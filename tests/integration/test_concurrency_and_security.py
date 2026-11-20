from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
from typing import TYPE_CHECKING, Any

import pytest

from database import DatabaseManager
from repositories import BookingRepository, SpaceRepository
from services import ConflictError, ReservationService

if TYPE_CHECKING:
    from flask import Flask
    from flask.testing import FlaskClient

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Concurrencia real sobre BEGIN IMMEDIATE
# ---------------------------------------------------------------------------


def test_concurrent_create_booking_allows_only_one_winner(
    db_file: Path,
    future_date_factory: Callable[[int], str],
) -> None:
    """8 hilos simultáneos sobre la misma franja producen 1 éxito, 7 ConflictError y 0 bloqueos SQLite."""
    db = DatabaseManager(db_file)
    db.init_schema()
    space_repo = SpaceRepository(db)
    booking_repo = BookingRepository(db)
    service = ReservationService(db, space_repo, booking_repo)

    space = space_repo.create(
        name="Sala Concurrencia",
        category="Sala de reuniones",
        floor="Planta 1",
        capacity=8,
        hourly_rate=40.0,
    )
    assert space.id is not None

    target_date = future_date_factory(30)
    workers = 8
    barrier = threading.Barrier(workers, timeout=10)

    def attempt_booking(idx: int) -> dict[str, Any]:
        barrier.wait()
        return service.create_booking(
            {
                "space_id": space.id,
                "title": f"Reserva concurrente #{idx}",
                "customer_name": f"Usuario {idx}",
                "customer_email": f"user{idx}@empresa.es",
                "attendees": 3,
                "booking_date": target_date,
                "start_time": "10:00",
                "end_time": "12:00",
                "notes": "Prueba de concurrencia",
            }
        )

    created: list[dict[str, Any]] = []
    conflicts: list[ConflictError] = []
    unexpected_errors: list[Exception] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(attempt_booking, i) for i in range(workers)]
        for fut in futures:
            try:
                created.append(fut.result())
            except ConflictError as exc:
                conflicts.append(exc)
            except Exception as exc:
                unexpected_errors.append(exc)

    assert unexpected_errors == [], f"Errores inesperados: {unexpected_errors!r}"
    assert len(created) == 1
    assert len(conflicts) == workers - 1

    persisted = booking_repo.list_filtered(
        {"space_id": space.id, "date": target_date}
    )
    assert len(persisted) == 1
    assert persisted[0]["id"] == created[0]["id"]


# ---------------------------------------------------------------------------
# Resistencia a inyección SQL
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql_payload",
    [
        "' OR '1'='1",
        "'; DROP TABLE bookings; --",
        "%') UNION SELECT 1,2 --",
    ],
)
def test_sql_injection_payloads_do_not_bypass_filters_or_corrupt_tables(
    client: FlaskClient,
    future_date_factory: Callable[[int], str],
    booking_payload_factory: Callable[..., dict[str, Any]],
    sql_payload: str,
) -> None:
    """Payloads SQLi en GET /api/spaces, GET /api/bookings y POST /api/bookings son inocuos."""
    spaces_resp = client.get("/api/spaces", query_string={"q": sql_payload})
    assert spaces_resp.status_code == 200
    assert spaces_resp.get_json()["spaces"] == []

    bookings_resp = client.get("/api/bookings", query_string={"q": sql_payload})
    assert bookings_resp.status_code == 200
    assert bookings_resp.get_json()["bookings"] == []

    # Guardar los payloads como texto literal en una reserva no altera el esquema ni las filas
    spaces = client.get("/api/spaces").get_json()["spaces"]
    assert len(spaces) == 6
    target_date = future_date_factory(35)

    create_resp = client.post(
        "/api/bookings",
        json=booking_payload_factory(
            space_id=spaces[0]["id"],
            booking_date=target_date,
            title=sql_payload,
            customer_name=sql_payload,
            notes=sql_payload,
        ),
    )
    assert create_resp.status_code == 201
    created = create_resp.get_json()
    assert created["title"] == sql_payload
    assert created["customer_name"] == sql_payload
    assert created["notes"] == sql_payload

    all_spaces = client.get("/api/spaces").get_json()["spaces"]
    all_bookings = client.get("/api/bookings").get_json()["bookings"]
    assert len(all_spaces) == 6
    assert len(all_bookings) == 15


# ---------------------------------------------------------------------------
# Contrato JSON uniforme de errores HTTP (404, 405, 500)
# ---------------------------------------------------------------------------


def test_http_404_and_405_return_uniform_json(client: FlaskClient) -> None:
    """Rutas inexistentes y métodos HTTP no permitidos devuelven JSON {'error': ...}."""
    not_found = client.get("/api/ruta-inexistente")
    assert not_found.status_code == 404
    assert not_found.is_json
    assert isinstance(not_found.get_json().get("error"), str)

    method_not_allowed_del = client.delete("/api/spaces/1")
    assert method_not_allowed_del.status_code == 405
    assert method_not_allowed_del.is_json
    assert isinstance(method_not_allowed_del.get_json().get("error"), str)

    method_not_allowed_post = client.post("/api/analytics", json={})
    assert method_not_allowed_post.status_code == 405
    assert method_not_allowed_post.is_json
    assert isinstance(method_not_allowed_post.get_json().get("error"), str)


def test_unexpected_runtime_error_returns_500_json_without_internal_leak(
    app: Flask,
    client: FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Una excepción no controlada en la API debe devolver HTTP 500 JSON sin HTML ni traceback."""
    monkeypatch.setitem(app.config, "TESTING", False)
    monkeypatch.setitem(app.config, "PROPAGATE_EXCEPTIONS", False)

    def explode(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("Fallo interno confidencial sqlite3")

    monkeypatch.setattr(ReservationService, "list_spaces", explode)

    resp = client.get("/api/spaces")
    body = resp.get_data(as_text=True)

    assert resp.status_code == 500
    assert resp.is_json is True
    payload = resp.get_json()
    assert isinstance(payload, dict)
    assert isinstance(payload.get("error"), str) and payload["error"].strip() != ""
    assert "<html" not in body.lower()
    assert "traceback" not in body.lower()
    assert "Fallo interno confidencial sqlite3" not in body
