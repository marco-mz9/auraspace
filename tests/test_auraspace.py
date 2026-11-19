from __future__ import annotations

import csv
from datetime import date, timedelta
import io
from pathlib import Path
import re
import sys
from typing import Any

import pytest

AURASPACE_DIR = Path(__file__).resolve().parent.parent
if str(AURASPACE_DIR) not in sys.path:
    sys.path.insert(0, str(AURASPACE_DIR))

from app import create_app


@pytest.fixture()
def db_file(tmp_path: Path) -> Path:
    """Devuelve una ruta de base de datos SQLite aislada por cada test."""
    return tmp_path / "test_auraspace.db"


@pytest.fixture()
def app(db_file: Path):
    """Crea una instancia aislada de la aplicación Flask para pruebas."""
    flask_app = create_app(db_path=db_file)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture()
def client(app):
    """Devuelve el cliente de pruebas HTTP de Flask."""
    return app.test_client()


def clean_future_date(days_ahead: int = 15) -> str:
    """Genera una fecha futura limpia en formato YYYY-MM-DD sin reservas semilla."""
    return (date.today() + timedelta(days=days_ahead)).isoformat()


def get_space_by_name(client, name: str) -> dict[str, Any]:
    """Busca y devuelve una sala del catálogo por su nombre exacto."""
    resp = client.get("/api/spaces")
    assert resp.status_code == 200
    spaces = resp.get_json()["spaces"]
    for space in spaces:
        if space["name"] == name:
            return space
    raise AssertionError(f"No se encontró la sala '{name}' en la semilla inicial.")


def make_booking_payload(
    space_id: int,
    booking_date: str,
    **overrides: Any,
) -> dict[str, Any]:
    """Construye un payload válido de reserva con posibles sobrescrituras."""
    payload: dict[str, Any] = {
        "space_id": space_id,
        "title": "Reunión de planificación",
        "customer_name": "Laura Martín",
        "customer_email": "laura.martin@empresa.es",
        "attendees": 4,
        "booking_date": booking_date,
        "start_time": "10:00",
        "end_time": "12:00",
        "notes": "Requiere pantalla HDMI",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# RF-01: Semilla idempotente y carga offline
# ---------------------------------------------------------------------------


def test_rf01_seed_is_idempotent(db_file: Path) -> None:
    """Arrancar dos veces sobre la misma BD no duplica salas ni reservas iniciales."""
    app_one = create_app(db_path=db_file)
    client_one = app_one.test_client()
    initial_spaces = client_one.get("/api/spaces").get_json()["spaces"]
    initial_bookings = client_one.get("/api/bookings").get_json()["bookings"]

    assert len(initial_spaces) == 6
    assert 12 <= len(initial_bookings) <= 15

    # Segundo arranque sobre el mismo db_file
    app_two = create_app(db_path=db_file)
    client_two = app_two.test_client()
    second_spaces = client_two.get("/api/spaces").get_json()["spaces"]
    second_bookings = client_two.get("/api/bookings").get_json()["bookings"]

    assert len(second_spaces) == 6
    assert len(second_bookings) == len(initial_bookings)


def test_rf01_index_serves_offline_html(client) -> None:
    """La raíz sirve HTML5 funcional y 100% offline sin URLs externas."""
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "AuraSpace" in html
    assert "http://" not in html.lower()
    assert "https://" not in html.lower()


# ---------------------------------------------------------------------------
# RF-02: Filtros de espacios y bloqueo al reservar en sala en mantenimiento
# ---------------------------------------------------------------------------


def test_rf02_space_filters_and_creation(client) -> None:
    """Los filtros de espacios y la creación de salas funcionan según contrato."""
    by_q = client.get("/api/spaces?q=proyector").get_json()["spaces"]
    assert len(by_q) == 2

    by_category = client.get(
        "/api/spaces?category=Sala+de+reuniones"
    ).get_json()["spaces"]
    assert len(by_category) == 2

    by_capacity = client.get("/api/spaces?min_capacity=12").get_json()["spaces"]
    assert all(space["capacity"] >= 12 for space in by_capacity)
    assert len(by_capacity) == 3

    created_resp = client.post(
        "/api/spaces",
        json={
            "name": "Sala Ático",
            "category": "Sala de reuniones",
            "floor": "Planta 4",
            "capacity": 10,
            "hourly_rate": 48.0,
            "equipment": "Pizarra interactiva, Wi-Fi 6",
        },
    )
    assert created_resp.status_code == 201
    assert created_resp.get_json()["is_active"] is True

    dup_resp = client.post(
        "/api/spaces",
        json={
            "name": "Sala Ático",
            "category": "Sala de reuniones",
            "floor": "Planta 4",
            "capacity": 10,
            "hourly_rate": 48.0,
        },
    )
    assert dup_resp.status_code == 409
    assert "error" in dup_resp.get_json()


def test_rf02_maintenance_space_blocks_booking(client) -> None:
    """Reservar en una sala marcada en mantenimiento devuelve HTTP 400."""
    sala = get_space_by_name(client, "Sala Aura")

    patch_resp = client.patch(
        f"/api/spaces/{sala['id']}",
        json={"is_active": False},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.get_json()["is_active"] is False

    active_spaces = client.get("/api/spaces?active_only=true").get_json()[
        "spaces"
    ]
    assert all(item["id"] != sala["id"] for item in active_spaces)

    booking_resp = client.post(
        "/api/bookings",
        json=make_booking_payload(
            sala["id"],
            clean_future_date(),
            start_time="09:00",
            end_time="10:30",
        ),
    )
    assert booking_resp.status_code == 400
    assert "error" in booking_resp.get_json()


# ---------------------------------------------------------------------------
# RF-03: Cálculo exacto de importe y código AURA-YYYYMMDD-XXXX
# ---------------------------------------------------------------------------


def test_rf03_exact_price_calculation_and_reference_code(client) -> None:
    """El importe equivale exactamente a duración * tarifa y genera AURA-YYYYMMDD-XXXX."""
    space_resp = client.post(
        "/api/spaces",
        json={
            "name": "Sala Decimal",
            "category": "Sala de reuniones",
            "floor": "Planta 2",
            "capacity": 8,
            "hourly_rate": 35.5,
            "equipment": "Monitor 4K",
        },
    )
    assert space_resp.status_code == 201
    space = space_resp.get_json()

    target_date = clean_future_date(20)
    compact_date = target_date.replace("-", "")

    resp_one = client.post(
        "/api/bookings",
        json=make_booking_payload(
            space["id"],
            target_date,
            start_time="10:00",
            end_time="11:30",
        ),
    )
    assert resp_one.status_code == 201
    b1 = resp_one.get_json()
    assert b1["duration_hours"] == 1.5
    assert b1["total_price"] == round(1.5 * 35.5, 2)  # 53.25
    assert re.fullmatch(
        rf"AURA-{compact_date}-[A-Z0-9]{{4}}",
        b1["reference_code"],
    )

    resp_two = client.post(
        "/api/bookings",
        json=make_booking_payload(
            space["id"],
            target_date,
            start_time="12:00",
            end_time="13:30",
            title="Segunda sesión",
        ),
    )
    assert resp_two.status_code == 201
    b2 = resp_two.get_json()
    assert b2["reference_code"] != b1["reference_code"]


# ---------------------------------------------------------------------------
# RF-04: Solapamientos (HTTP 409)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overlap_start", "overlap_end"),
    [
        ("10:00", "12:00"),  # Solapamiento total exacto
        ("09:00", "11:00"),  # Parcial al inicio
        ("11:00", "13:00"),  # Parcial al final
        ("10:30", "11:30"),  # Contenido dentro de la reserva
        ("09:30", "12:30"),  # Envolvente de la reserva existente
    ],
)
def test_rf04_overlapping_bookings_return_409(
    client,
    overlap_start: str,
    overlap_end: str,
) -> None:
    """Cualquier solapamiento sobre una reserva activa devuelve HTTP 409."""
    sala = get_space_by_name(client, "Sala Aura")
    target_date = clean_future_date(16)

    base_resp = client.post(
        "/api/bookings",
        json=make_booking_payload(
            sala["id"],
            target_date,
            start_time="10:00",
            end_time="12:00",
        ),
    )
    assert base_resp.status_code == 201

    conflict_resp = client.post(
        "/api/bookings",
        json=make_booking_payload(
            sala["id"],
            target_date,
            start_time=overlap_start,
            end_time=overlap_end,
            title="Intento solapado",
        ),
    )
    assert conflict_resp.status_code == 409
    assert "error" in conflict_resp.get_json()


def test_rf04_same_slot_different_space_is_allowed(client) -> None:
    """Reservar el mismo horario en otra sala distinta devuelve HTTP 201."""
    sala_aura = get_space_by_name(client, "Sala Aura")
    estudio_zenith = get_space_by_name(client, "Estudio Zenith")
    target_date = clean_future_date(16)

    r1 = client.post(
        "/api/bookings",
        json=make_booking_payload(
            sala_aura["id"],
            target_date,
            start_time="10:00",
            end_time="12:00",
        ),
    )
    r2 = client.post(
        "/api/bookings",
        json=make_booking_payload(
            estudio_zenith["id"],
            target_date,
            start_time="10:00",
            end_time="12:00",
        ),
    )
    assert r1.status_code == 201
    assert r2.status_code == 201


# ---------------------------------------------------------------------------
# RF-05: Reservas contiguas exactas (HTTP 201)
# ---------------------------------------------------------------------------


def test_rf05_contiguous_bookings_are_accepted(client) -> None:
    """Las reservas contiguas exactas (10:00-11:00 y 11:00-12:00) no solapan."""
    sala = get_space_by_name(client, "Estudio Zenith")
    target_date = clean_future_date(17)

    first = client.post(
        "/api/bookings",
        json=make_booking_payload(
            sala["id"],
            target_date,
            start_time="10:00",
            end_time="11:00",
            title="Bloque 1",
        ),
    )
    second = client.post(
        "/api/bookings",
        json=make_booking_payload(
            sala["id"],
            target_date,
            start_time="11:00",
            end_time="12:00",
            title="Bloque 2",
        ),
    )
    previous = client.post(
        "/api/bookings",
        json=make_booking_payload(
            sala["id"],
            target_date,
            start_time="09:00",
            end_time="10:00",
            title="Bloque previo",
        ),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert previous.status_code == 201


# ---------------------------------------------------------------------------
# RF-06: Cancelación, bloqueo de edición y reactivación con conflicto
# ---------------------------------------------------------------------------


def test_rf06_cancellation_frees_slot_blocks_edit_and_checks_reactivation(
    client,
) -> None:
    """Cancelar libera la franja, bloquea edición (400) y valida conflicto al reactivar (409)."""
    sala = get_space_by_name(client, "Sala Aura")
    target_date = clean_future_date(18)

    created = client.post(
        "/api/bookings",
        json=make_booking_payload(
            sala["id"],
            target_date,
            start_time="10:00",
            end_time="12:00",
        ),
    ).get_json()

    cancel_resp = client.patch(
        f"/api/bookings/{created['id']}/status",
        json={"status": "cancelada", "notes": "Cancelada por el cliente"},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.get_json()["status"] == "cancelada"

    # Prohibido editar una reserva cancelada
    edit_cancelled_resp = client.put(
        f"/api/bookings/{created['id']}",
        json=make_booking_payload(
            sala["id"],
            target_date,
            start_time="10:00",
            end_time="11:00",
            title="Intento inválido",
        ),
    )
    assert edit_cancelled_resp.status_code == 400
    assert "error" in edit_cancelled_resp.get_json()

    # La franja quedó libre para una nueva reserva
    replacement_resp = client.post(
        "/api/bookings",
        json=make_booking_payload(
            sala["id"],
            target_date,
            start_time="10:30",
            end_time="11:30",
            title="Nueva reserva en franja liberada",
        ),
    )
    assert replacement_resp.status_code == 201
    replacement = replacement_resp.get_json()

    # Reactivar mientras está ocupada la franja devuelve 409
    reactivate_conflict = client.patch(
        f"/api/bookings/{created['id']}/status",
        json={"status": "confirmada"},
    )
    assert reactivate_conflict.status_code == 409
    assert "error" in reactivate_conflict.get_json()

    # Si se cancela la reserva que ocupa la franja, ya permite reactivar
    assert (
        client.patch(
            f"/api/bookings/{replacement['id']}/status",
            json={"status": "cancelada"},
        ).status_code
        == 200
    )
    reactivate_ok = client.patch(
        f"/api/bookings/{created['id']}/status",
        json={"status": "confirmada"},
    )
    assert reactivate_ok.status_code == 200
    assert reactivate_ok.get_json()["status"] == "confirmada"


# ---------------------------------------------------------------------------
# RF-07: Edición de reserva activa sin falso auto-conflicto (HTTP 200)
# ---------------------------------------------------------------------------


def test_rf07_edit_active_booking_without_false_self_conflict(client) -> None:
    """Editar una reserva activa dentro de su propia franja devuelve HTTP 200."""
    sala = get_space_by_name(client, "Sala Aura")  # 35.0 €/h
    target_date = clean_future_date(19)

    created = client.post(
        "/api/bookings",
        json=make_booking_payload(
            sala["id"],
            target_date,
            start_time="10:00",
            end_time="12:00",
        ),
    ).get_json()

    # Desplazar solapando su propio rango anterior (10:00-12:00 -> 10:30-12:30)
    edit_resp = client.put(
        f"/api/bookings/{created['id']}",
        json=make_booking_payload(
            sala["id"],
            target_date,
            start_time="10:30",
            end_time="13:00",
            title="Comité ampliado",
            attendees=6,
        ),
    )
    assert edit_resp.status_code == 200
    updated = edit_resp.get_json()
    assert updated["reference_code"] == created["reference_code"]
    assert updated["title"] == "Comité ampliado"
    assert updated["duration_hours"] == 2.5
    assert updated["total_price"] == round(2.5 * 35.0, 2)

    # Mantener exactamente el mismo horario cambiando solo datos de contacto
    same_slot_edit = client.put(
        f"/api/bookings/{created['id']}",
        json=make_booking_payload(
            sala["id"],
            target_date,
            start_time="10:30",
            end_time="13:00",
            customer_name="Carlos Navarro",
        ),
    )
    assert same_slot_edit.status_code == 200

    # Invadir otra reserva distinta sigue devolviendo 409
    other = client.post(
        "/api/bookings",
        json=make_booking_payload(
            sala["id"],
            target_date,
            start_time="14:00",
            end_time="15:00",
            title="Otra reserva",
        ),
    )
    assert other.status_code == 201

    collide_resp = client.put(
        f"/api/bookings/{created['id']}",
        json=make_booking_payload(
            sala["id"],
            target_date,
            start_time="13:30",
            end_time="14:30",
        ),
    )
    assert collide_resp.status_code == 409


# ---------------------------------------------------------------------------
# RF-08: Validaciones estrictas de entrada (HTTP 400)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"start_time": "07:30", "end_time": "08:30"},  # Antes de 08:00
        {"start_time": "20:30", "end_time": "21:30"},  # Después de 21:00
        {"start_time": "10:00", "end_time": "10:00"},  # Fin == Inicio
        {"start_time": "12:00", "end_time": "11:00"},  # Fin < Inicio
        {"start_time": "09:15", "end_time": "10:00"},  # Minuto no múltiplo de 30
        {"start_time": "09:00", "end_time": "10:45"},  # Fin no múltiplo de 30
        {"start_time": "08:00", "end_time": "16:30"},  # Duración > 8 horas (8.5h)
        {"attendees": 9},  # Supera aforo de Sala Aura (8)
        {"attendees": 0},  # Asistentes <= 0
        {"customer_email": "correo-sin-arroba"},  # Email inválido
        {"customer_email": "nombre@sin-tld"},  # Email sin dominio TLD
        {"booking_date": "2026-02-30"},  # Fecha inexistente en calendario
    ],
)
def test_rf08_invalid_booking_inputs_return_400(
    client, overrides: dict[str, Any]
) -> None:
    """Entradas fuera de reglas horarias, aforo, fecha o email devuelven HTTP 400."""
    sala = get_space_by_name(client, "Sala Aura")  # capacity = 8
    payload = make_booking_payload(sala["id"], clean_future_date(21))
    payload.update(overrides)
    resp = client.post("/api/bookings", json=payload)
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_rf08_exact_8_hour_max_duration_is_accepted(client) -> None:
    """La duración máxima exacta de 8 horas (08:00-16:00) se acepta con HTTP 201."""
    sala = get_space_by_name(client, "Sala Aura")
    resp = client.post(
        "/api/bookings",
        json=make_booking_payload(
            sala["id"],
            clean_future_date(22),
            start_time="08:00",
            end_time="16:00",
        ),
    )
    assert resp.status_code == 201
    assert resp.get_json()["duration_hours"] == 8.0


# ---------------------------------------------------------------------------
# RF-09: Disponibilidad (/api/availability) con exclude_booking_id
# ---------------------------------------------------------------------------


def test_rf09_availability_26_slots_and_exclude_booking_id(client) -> None:
    """Devuelve 26 bloques (08:00-21:00) e ignora la reserva pasada en exclude_booking_id."""
    sala = get_space_by_name(client, "Cabina Focus A")
    target_date = clean_future_date(23)

    created = client.post(
        "/api/bookings",
        json=make_booking_payload(
            sala["id"],
            target_date,
            start_time="10:00",
            end_time="11:30",
            attendees=1,
        ),
    ).get_json()

    avail = client.get(
        f"/api/availability?space_id={sala['id']}&date={target_date}"
    )
    assert avail.status_code == 200
    data = avail.get_json()
    assert data["total_slots"] == 26
    assert data["occupied_slots"] == 3
    assert data["available_slots"] == 23
    assert data["slots"][0]["start_time"] == "08:00"
    assert data["slots"][-1]["end_time"] == "21:00"

    occupied_ranges = [
        f"{slot['start_time']}-{slot['end_time']}"
        for slot in data["slots"]
        if slot["occupied"]
    ]
    assert occupied_ranges == ["10:00-10:30", "10:30-11:00", "11:00-11:30"]

    # Excluyendo la propia reserva quedan los 26 bloques libres
    avail_excluded = client.get(
        f"/api/availability?space_id={sala['id']}&date={target_date}"
        f"&exclude_booking_id={created['id']}"
    )
    assert avail_excluded.status_code == 200
    excluded_data = avail_excluded.get_json()
    assert excluded_data["total_slots"] == 26
    assert excluded_data["occupied_slots"] == 0
    assert excluded_data["available_slots"] == 26


# ---------------------------------------------------------------------------
# RF-10: Analítica (/api/analytics) y exportación CSV (/api/bookings/export)
# ---------------------------------------------------------------------------


def test_rf10_analytics_metrics_and_breakdown(client) -> None:
    """La analítica excluye canceladas de ingresos/ocupación y desglosa por sala y hora."""
    sala = get_space_by_name(client, "Sala Aura")  # 35.0 €/h
    target_date = clean_future_date(24)

    active_b = client.post(
        "/api/bookings",
        json=make_booking_payload(
            sala["id"],
            target_date,
            start_time="09:00",
            end_time="11:00",  # 2h -> 70.0 €
            title="Sesión Analítica Activa",
        ),
    ).get_json()

    cancelled_b = client.post(
        "/api/bookings",
        json=make_booking_payload(
            sala["id"],
            target_date,
            start_time="14:00",
            end_time="16:00",
            title="Sesión Analítica Cancelada",
        ),
    ).get_json()
    assert (
        client.patch(
            f"/api/bookings/{cancelled_b['id']}/status",
            json={"status": "cancelada"},
        ).status_code
        == 200
    )

    analytics_resp = client.get(f"/api/analytics?date={target_date}")
    assert analytics_resp.status_code == 200
    analytics = analytics_resp.get_json()

    all_bookings = client.get("/api/bookings").get_json()["bookings"]
    expected_total_revenue = round(
        sum(
            b["total_price"]
            for b in all_bookings
            if b["status"] != "cancelada"
        ),
        2,
    )

    assert analytics["target_date"] == target_date
    assert analytics["total_revenue"] == expected_total_revenue
    assert analytics["target_date_revenue"] == active_b["total_price"]
    assert sum(analytics["status_counts"].values()) == analytics["total_bookings"]
    # 2h activas de 6 salas * 13h = 78h disponibles
    assert analytics["occupancy_today_pct"] == round((2.0 / 78.0) * 100, 1)
    assert len(analytics["by_space"]) == 6
    assert len(analytics["by_hour"]) == 13
    assert analytics["by_hour"][0]["hour"] == "08:00"
    assert analytics["by_hour"][-1]["hour"] == "20:00"


def test_rf10_export_csv_bom_and_filters(client) -> None:
    """La exportación CSV incluye BOM UTF-8 (\ufeff), tildes/€ y respeta filtros."""
    sala = get_space_by_name(client, "Sala Aura")
    target_date = clean_future_date(25)

    created = client.post(
        "/api/bookings",
        json=make_booking_payload(
            sala["id"],
            target_date,
            title="Sesión Ñandú & Café",
            customer_name="Inés Álvarez",
            customer_email="ines@auraspace.es",
            start_time="11:00",
            end_time="12:30",
        ),
    ).get_json()

    resp = client.get(
        f"/api/bookings/export?date={target_date}&status=confirmada&q=Álvarez"
    )
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "text/csv; charset=utf-8"
    assert resp.data.startswith(b"\xef\xbb\xbf")

    csv_text = resp.data.decode("utf-8")
    assert csv_text.startswith("\ufeff")

    rows = list(csv.reader(io.StringIO(csv_text.lstrip("\ufeff"))))
    assert len(rows) == 2
    headers, data_row = rows[0], rows[1]
    assert "Código" in headers
    assert "Importe (€)" in headers
    assert data_row[0] == created["reference_code"]
    assert "Inés Álvarez" in data_row
    assert "Sesión Ñandú & Café" in data_row
