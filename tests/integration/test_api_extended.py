from __future__ import annotations

from collections.abc import Callable
import csv
import io
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from flask.testing import FlaskClient

pytestmark = pytest.mark.integration


def _get_space(client: FlaskClient, name: str) -> dict[str, Any]:
    """Busca una sala del catálogo por nombre exacto."""
    resp = client.get("/api/spaces")
    assert resp.status_code == 200
    for space in resp.get_json()["spaces"]:
        if space["name"] == name:
            return space
    raise AssertionError(f"No se encontró la sala '{name}'.")


# ---------------------------------------------------------------------------
# GET /api/spaces, POST /api/spaces y PATCH /api/spaces/<id>
# ---------------------------------------------------------------------------


def test_get_spaces_ordering_combined_filters_and_invalid_min_capacity(
    client: FlaskClient,
) -> None:
    """GET /api/spaces ordena activas primero, combina filtros y valida min_capacity."""
    auditorio = _get_space(client, "Auditorio Horizonte")
    patch_resp = client.patch(
        f"/api/spaces/{auditorio['id']}",
        json={"is_active": False},
    )
    assert patch_resp.status_code == 200

    all_spaces = client.get("/api/spaces").get_json()["spaces"]
    assert all_spaces[-1]["id"] == auditorio["id"]
    assert all_spaces[-1]["is_active"] is False
    active_names = [s["name"] for s in all_spaces[:-1]]
    assert all(s["is_active"] is True for s in all_spaces[:-1])
    assert active_names == sorted(active_names)

    # Filtros combinados
    filtered = client.get(
        "/api/spaces",
        query_string={
            "q": "proyector",
            "category": "Sala de reuniones",
            "min_capacity": "10",
            "active_only": "true",
        },
    )
    assert filtered.status_code == 200
    assert [s["name"] for s in filtered.get_json()["spaces"]] == ["Estudio Zenith"]

    # min_capacity inválido -> 400 JSON
    for bad_cap in ("0", "-3", "abc", "4.5"):
        err_resp = client.get("/api/spaces", query_string={"min_capacity": bad_cap})
        assert err_resp.status_code == 400
        assert err_resp.is_json
        assert "error" in err_resp.get_json()


@pytest.mark.parametrize(
    "payload",
    [
        {
            "name": "   ",
            "category": "Sala de reuniones",
            "floor": "Planta 1",
            "capacity": 6,
            "hourly_rate": 30.0,
        },
        {
            "name": "Sala Válida",
            "category": "",
            "floor": "Planta 1",
            "capacity": 6,
            "hourly_rate": 30.0,
        },
        {
            "name": "Sala Válida",
            "category": "Sala de reuniones",
            "floor": "  ",
            "capacity": 6,
            "hourly_rate": 30.0,
        },
        {
            "name": "Sala Válida",
            "category": "Sala de reuniones",
            "floor": "Planta 1",
            "capacity": 0,
            "hourly_rate": 30.0,
        },
        {
            "name": "Sala Válida",
            "category": "Sala de reuniones",
            "floor": "Planta 1",
            "capacity": -2,
            "hourly_rate": 30.0,
        },
        {
            "name": "Sala Válida",
            "category": "Sala de reuniones",
            "floor": "Planta 1",
            "capacity": 6,
            "hourly_rate": -5,
        },
        {
            "name": "Sala Válida",
            "category": "Sala de reuniones",
            "floor": "Planta 1",
            "capacity": 6,
            "hourly_rate": "NaN",
        },
        {
            "name": "Sala Válida",
            "category": "Sala de reuniones",
            "floor": "Planta 1",
            "capacity": 6,
            "hourly_rate": "inf",
        },
        {
            "name": "Sala Válida",
            "category": "Sala de reuniones",
            "floor": "Planta 1",
            "capacity": 6,
            "hourly_rate": "-inf",
        },
    ],
)
def test_post_spaces_validation_errors_return_400(
    client: FlaskClient, payload: dict[str, Any]
) -> None:
    """POST /api/spaces rechaza campos vacíos, capacity<=0 y hourly_rate inválidos."""
    resp = client.post("/api/spaces", json=payload)
    assert resp.status_code == 400
    assert resp.is_json
    assert "error" in resp.get_json()


def test_post_spaces_non_json_and_duplicate_conflict(client: FlaskClient) -> None:
    """POST /api/spaces devuelve 400 para cuerpo no JSON y 409 para nombre duplicado."""
    plain_resp = client.post(
        "/api/spaces", data="texto plano", content_type="text/plain"
    )
    assert plain_resp.status_code == 400
    assert "error" in plain_resp.get_json()

    malformed_resp = client.post(
        "/api/spaces", data="{bad json", content_type="application/json"
    )
    assert malformed_resp.status_code == 400
    assert "error" in malformed_resp.get_json()

    list_resp = client.post("/api/spaces", json=["no-es-objeto"])
    assert list_resp.status_code == 400
    assert "error" in list_resp.get_json()

    dup_resp = client.post(
        "/api/spaces",
        json={
            "name": "Sala Aura",
            "category": "Sala de reuniones",
            "floor": "Planta 1",
            "capacity": 8,
            "hourly_rate": 35.0,
        },
    )
    assert dup_resp.status_code == 409
    assert "error" in dup_resp.get_json()


def test_patch_space_status_variants_and_errors(client: FlaskClient) -> None:
    """PATCH /api/spaces/<id> acepta booleanos/strings y rechaza faltantes/inválidos/404."""
    sala = _get_space(client, "Sala Aura")

    for raw_flag, expected in [
        (False, False),
        (True, True),
        ("false", False),
        ("true", True),
        ("0", False),
        ("sí", True),
        ("no", False),
        ("yes", True),
    ]:
        resp = client.patch(
            f"/api/spaces/{sala['id']}",
            json={"is_active": raw_flag},
        )
        assert resp.status_code == 200
        assert resp.get_json()["is_active"] is expected

    missing_resp = client.patch(f"/api/spaces/{sala['id']}", json={})
    assert missing_resp.status_code == 400
    assert "error" in missing_resp.get_json()

    for bad_flag in ("talvez", 2, None):
        bad_resp = client.patch(
            f"/api/spaces/{sala['id']}",
            json={"is_active": bad_flag},
        )
        assert bad_resp.status_code == 400
        assert "error" in bad_resp.get_json()

    not_found_resp = client.patch(
        "/api/spaces/99999",
        json={"is_active": False},
    )
    assert not_found_resp.status_code == 404
    assert "error" in not_found_resp.get_json()


# ---------------------------------------------------------------------------
# GET /api/availability y GET /api/schedule
# ---------------------------------------------------------------------------


def test_availability_marks_all_slots_unavailable_when_space_in_maintenance(
    client: FlaskClient,
    future_date_factory: Callable[[int], str],
) -> None:
    """Una sala en mantenimiento debe reportar los 26 bloques como no disponibles."""
    sala = _get_space(client, "Sala Aura")
    patch_resp = client.patch(
        f"/api/spaces/{sala['id']}",
        json={"is_active": False},
    )
    assert patch_resp.status_code == 200

    target_date = future_date_factory(20)
    resp = client.get(
        "/api/availability",
        query_string={"space_id": sala["id"], "date": target_date},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total_slots"] == 26
    assert data["available_slots"] == 0
    assert data["occupied_slots"] == 26
    assert all(
        slot["available"] is False and slot["occupied"] is True
        for slot in data["slots"]
    )


def test_availability_validation_and_not_found_errors(
    client: FlaskClient,
    future_date_factory: Callable[[int], str],
) -> None:
    """GET /api/availability valida space_id, date y exclude_booking_id."""
    target_date = future_date_factory(20)

    assert client.get("/api/availability").status_code == 400
    assert (
        client.get(
            "/api/availability",
            query_string={"space_id": "abc", "date": target_date},
        ).status_code
        == 400
    )
    assert (
        client.get(
            "/api/availability",
            query_string={"space_id": "0", "date": target_date},
        ).status_code
        == 400
    )
    assert (
        client.get(
            "/api/availability",
            query_string={"space_id": 1, "date": "2026-02-30"},
        ).status_code
        == 400
    )
    assert (
        client.get(
            "/api/availability",
            query_string={
                "space_id": 1,
                "date": target_date,
                "exclude_booking_id": "abc",
            },
        ).status_code
        == 400
    )
    assert (
        client.get(
            "/api/availability",
            query_string={
                "space_id": 1,
                "date": target_date,
                "exclude_booking_id": "0",
            },
        ).status_code
        == 400
    )

    missing_space = client.get(
        "/api/availability",
        query_string={"space_id": 99999, "date": target_date},
    )
    assert missing_space.status_code == 404
    assert "error" in missing_space.get_json()


def test_get_schedule_ordering_excludes_cancelled_and_validates_date(
    client: FlaskClient,
    future_date_factory: Callable[[int], str],
    booking_payload_factory: Callable[..., dict[str, Any]],
) -> None:
    """GET /api/schedule ordena cronológicamente, excluye canceladas y calcula ocupación."""
    sala = _get_space(client, "Sala Aura")
    target_date = future_date_factory(21)

    for start_t, end_t, title in [
        ("16:00", "17:00", "Tarde"),
        ("09:00", "10:30", "Mañana"),
        ("12:00", "13:00", "Mediodía"),
    ]:
        r = client.post(
            "/api/bookings",
            json=booking_payload_factory(
                space_id=sala["id"],
                booking_date=target_date,
                start_time=start_t,
                end_time=end_t,
                title=title,
            ),
        )
        assert r.status_code == 201

    cancelled = client.post(
        "/api/bookings",
        json=booking_payload_factory(
            space_id=sala["id"],
            booking_date=target_date,
            start_time="14:00",
            end_time="15:00",
            title="Cancelada en agenda",
        ),
    ).get_json()
    assert (
        client.patch(
            f"/api/bookings/{cancelled['id']}/status",
            json={"status": "cancelada"},
        ).status_code
        == 200
    )

    sched_resp = client.get("/api/schedule", query_string={"date": target_date})
    assert sched_resp.status_code == 200
    sched = sched_resp.get_json()
    assert sched["booking_date"] == target_date
    assert sched["open_time"] == "08:00"
    assert sched["close_time"] == "21:00"

    sala_entry = next(s for s in sched["spaces"] if s["id"] == sala["id"])
    assert [b["start_time"] for b in sala_entry["bookings"]] == [
        "09:00",
        "12:00",
        "16:00",
    ]
    assert all(b["status"] != "cancelada" for b in sala_entry["bookings"])
    assert sala_entry["booked_hours"] == 3.5
    assert sala_entry["occupancy_pct"] == round((3.5 / 13.0) * 100, 1)

    for bad_date in ("2026-02-30", "invalida"):
        bad_resp = client.get("/api/schedule", query_string={"date": bad_date})
        assert bad_resp.status_code == 400
        assert "error" in bad_resp.get_json()


# ---------------------------------------------------------------------------
# PUT /api/bookings/<id> y PATCH /api/bookings/<id>/status
# ---------------------------------------------------------------------------


def test_put_booking_partial_space_change_and_error_cases(
    client: FlaskClient,
    future_date_factory: Callable[[int], str],
    booking_payload_factory: Callable[..., dict[str, Any]],
) -> None:
    """PUT /api/bookings/<id> soporta edición parcial, cambio de sala y valida reglas."""
    sala_aura = _get_space(client, "Sala Aura")  # aforo 8, 35 €/h
    estudio_zenith = _get_space(client, "Estudio Zenith")  # aforo 12, 50 €/h
    cabina = _get_space(client, "Cabina Focus A")  # aforo 2, 14 €/h
    taller = _get_space(client, "Taller Creativo Brisa")  # aforo 16, 60 €/h
    target_date = future_date_factory(22)

    created = client.post(
        "/api/bookings",
        json=booking_payload_factory(
            space_id=sala_aura["id"],
            booking_date=target_date,
            start_time="09:00",
            end_time="11:00",
            attendees=5,
            title="Original",
        ),
    ).get_json()

    # Actualización parcial: solo título
    only_title = client.put(
        f"/api/bookings/{created['id']}",
        json={"title": "Título parcial"},
    )
    assert only_title.status_code == 200
    assert only_title.get_json()["title"] == "Título parcial"
    assert only_title.get_json()["start_time"] == "09:00"
    assert only_title.get_json()["total_price"] == 70.0

    # Actualización parcial: solo horario (recalcula tarifa)
    only_hours = client.put(
        f"/api/bookings/{created['id']}",
        json={"start_time": "10:00", "end_time": "13:00"},
    )
    assert only_hours.status_code == 200
    assert only_hours.get_json()["duration_hours"] == 3.0
    assert only_hours.get_json()["total_price"] == 105.0

    # Cambio a Estudio Zenith (50.0 €/h * 3.0 h = 150.0 €)
    change_space = client.put(
        f"/api/bookings/{created['id']}",
        json={"space_id": estudio_zenith["id"]},
    )
    assert change_space.status_code == 200
    assert change_space.get_json()["space_name"] == "Estudio Zenith"
    assert change_space.get_json()["total_price"] == 150.0

    # Rechazo 400 si sala destino supera aforo (attendees=5 > capacity=2)
    over_capacity = client.put(
        f"/api/bookings/{created['id']}",
        json={"space_id": cabina["id"]},
    )
    assert over_capacity.status_code == 400
    assert "error" in over_capacity.get_json()

    # Rechazo 400 si sala destino está en mantenimiento
    assert (
        client.patch(
            f"/api/spaces/{taller['id']}", json={"is_active": False}
        ).status_code
        == 200
    )
    inactive_target = client.put(
        f"/api/bookings/{created['id']}",
        json={"space_id": taller["id"]},
    )
    assert inactive_target.status_code == 400
    assert "error" in inactive_target.get_json()

    # 404 si reserva o sala destino no existen
    assert (
        client.put("/api/bookings/99999", json={"title": "Fantasma"}).status_code
        == 404
    )
    assert (
        client.put(
            f"/api/bookings/{created['id']}", json={"space_id": 99999}
        ).status_code
        == 404
    )

    # 409 si solapa con otra reserva en la sala destino (Sala Aura)
    other = client.post(
        "/api/bookings",
        json=booking_payload_factory(
            space_id=sala_aura["id"],
            booking_date=target_date,
            start_time="11:00",
            end_time="12:30",
            title="Ocupando Aura",
        ),
    )
    assert other.status_code == 201

    overlap_resp = client.put(
        f"/api/bookings/{created['id']}",
        json={"space_id": sala_aura["id"]},
    )
    assert overlap_resp.status_code == 409
    assert "error" in overlap_resp.get_json()


@pytest.mark.parametrize("target_status", ["confirmada", "completada"])
def test_patch_booking_status_reactivation_guards_and_errors(
    client: FlaskClient,
    future_date_factory: Callable[[int], str],
    booking_payload_factory: Callable[..., dict[str, Any]],
    target_status: str,
) -> None:
    """Reactivar desde cancelada (a confirmada o completada) falla con 400 en mantenimiento y 409 en solape."""
    sala = _get_space(client, "Sala Aura")
    target_date = future_date_factory(23)

    b1 = client.post(
        "/api/bookings",
        json=booking_payload_factory(
            space_id=sala["id"],
            booking_date=target_date,
            start_time="10:00",
            end_time="12:00",
        ),
    ).get_json()
    assert (
        client.patch(
            f"/api/bookings/{b1['id']}/status", json={"status": "cancelada"}
        ).status_code
        == 200
    )

    # 1) Conflicto 409 si otra reserva ocupó la franja
    b2 = client.post(
        "/api/bookings",
        json=booking_payload_factory(
            space_id=sala["id"],
            booking_date=target_date,
            start_time="11:00",
            end_time="13:00",
            title="Ocupante",
        ),
    ).get_json()
    assert (
        client.patch(
            f"/api/bookings/{b1['id']}/status", json={"status": target_status}
        ).status_code
        == 409
    )

    # Liberar franja cancelando b2
    assert (
        client.patch(
            f"/api/bookings/{b2['id']}/status", json={"status": "cancelada"}
        ).status_code
        == 200
    )

    # 2) Sala en mantenimiento debe bloquear la reactivación con HTTP 400
    assert (
        client.patch(
            f"/api/spaces/{sala['id']}", json={"is_active": False}
        ).status_code
        == 200
    )
    reactivate_inactive = client.patch(
        f"/api/bookings/{b1['id']}/status",
        json={"status": target_status},
    )
    assert reactivate_inactive.status_code == 400
    assert "error" in reactivate_inactive.get_json()


def test_patch_booking_status_invalid_inputs_and_404(client: FlaskClient) -> None:
    """PATCH /api/bookings/<id>/status devuelve 400 ante estado inválido/ausente y 404 si no existe."""
    bookings = client.get("/api/bookings").get_json()["bookings"]
    booking_id = bookings[0]["id"]

    assert (
        client.patch(f"/api/bookings/{booking_id}/status", json={}).status_code == 400
    )
    assert (
        client.patch(
            f"/api/bookings/{booking_id}/status", json={"status": "pendiente"}
        ).status_code
        == 400
    )
    assert (
        client.patch(
            f"/api/bookings/{booking_id}/status", json={"status": 123}
        ).status_code
        == 400
    )
    assert (
        client.patch(
            "/api/bookings/99999/status", json={"status": "cancelada"}
        ).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# GET /api/analytics y GET /api/bookings/export
# ---------------------------------------------------------------------------


def test_analytics_empty_database_returns_zero_metrics(
    empty_client: FlaskClient,
    future_date_factory: Callable[[int], str],
) -> None:
    """Sobre una BD vacía, GET /api/analytics devuelve ceros sin ZeroDivisionError."""
    target_date = future_date_factory(25)
    resp = empty_client.get("/api/analytics", query_string={"date": target_date})
    assert resp.status_code == 200

    data = resp.get_json()
    assert data["target_date"] == target_date
    assert data["total_bookings"] == 0
    assert data["active_bookings"] == 0
    assert data["total_revenue"] == 0.0
    assert data["target_date_revenue"] == 0.0
    assert data["total_hours"] == 0.0
    assert data["occupancy_today_pct"] == 0.0
    assert data["active_spaces_count"] == 0
    assert data["total_spaces_count"] == 0
    assert data["status_counts"] == {
        "confirmada": 0,
        "completada": 0,
        "cancelada": 0,
    }
    assert data["by_space"] == []
    assert len(data["by_hour"]) == 13
    assert all(
        h["bookings_count"] == 0 and h["today_count"] == 0 and h["occupancy_pct"] == 0.0
        for h in data["by_hour"]
    )


def test_analytics_with_inactive_space_never_exceeds_100_percent(
    empty_client: FlaskClient,
    future_date_factory: Callable[[int], str],
    booking_payload_factory: Callable[..., dict[str, Any]],
) -> None:
    """La ocupación del día y por franja horaria solo computa salas activas y nunca supera 100%."""
    target_date = future_date_factory(26)

    s_active = empty_client.post(
        "/api/spaces",
        json={
            "name": "Sala Activa",
            "category": "Sala de reuniones",
            "floor": "Planta 1",
            "capacity": 8,
            "hourly_rate": 40.0,
        },
    ).get_json()
    s_inactive = empty_client.post(
        "/api/spaces",
        json={
            "name": "Sala Inactiva Después",
            "category": "Sala de reuniones",
            "floor": "Planta 2",
            "capacity": 8,
            "hourly_rate": 40.0,
        },
    ).get_json()

    # 6 horas en la sala activa (09:00-15:00) y 8 horas en la que luego se desactiva (09:00-17:00)
    assert (
        empty_client.post(
            "/api/bookings",
            json=booking_payload_factory(
                space_id=s_active["id"],
                booking_date=target_date,
                start_time="09:00",
                end_time="15:00",
                title="Reserva Activa",
            ),
        ).status_code
        == 201
    )
    assert (
        empty_client.post(
            "/api/bookings",
            json=booking_payload_factory(
                space_id=s_inactive["id"],
                booking_date=target_date,
                start_time="09:00",
                end_time="17:00",
                title="Reserva Sala Luego Inactiva",
            ),
        ).status_code
        == 201
    )

    assert (
        empty_client.patch(
            f"/api/spaces/{s_inactive['id']}", json={"is_active": False}
        ).status_code
        == 200
    )

    analytics = empty_client.get(
        "/api/analytics", query_string={"date": target_date}
    ).get_json()

    assert analytics["active_spaces_count"] == 1
    assert analytics["total_spaces_count"] == 2
    assert 0.0 <= analytics["occupancy_today_pct"] <= 100.0
    assert analytics["occupancy_today_pct"] == round((6.0 / 13.0) * 100, 1)

    for hour_slot in analytics["by_hour"]:
        assert 0.0 <= hour_slot["occupancy_pct"] <= 100.0

    slot_15 = next(h for h in analytics["by_hour"] if h["hour"] == "15:00")
    assert slot_15["today_count"] == 0
    assert slot_15["occupancy_pct"] == 0.0


def test_export_csv_rfc4180_escaping_bom_and_encoding(
    client: FlaskClient,
    future_date_factory: Callable[[int], str],
    booking_payload_factory: Callable[..., dict[str, Any]],
) -> None:
    """GET /api/bookings/export escapa comas, comillas y tildes según RFC 4180 con BOM UTF-8."""
    sala = _get_space(client, "Sala Aura")
    target_date = future_date_factory(27)

    special_title = 'Comité "Q4", diseño & café'
    special_customer = "Óscar Muñoz, Jr."
    special_notes = 'Traer "adaptador", café y agua'

    created = client.post(
        "/api/bookings",
        json=booking_payload_factory(
            space_id=sala["id"],
            booking_date=target_date,
            title=special_title,
            customer_name=special_customer,
            notes=special_notes,
            start_time="10:00",
            end_time="11:30",
        ),
    )
    assert created.status_code == 201
    ref_code = created.get_json()["reference_code"]

    export_resp = client.get(
        "/api/bookings/export", query_string={"date": target_date}
    )
    assert export_resp.status_code == 200
    assert export_resp.headers["Content-Type"] == "text/csv; charset=utf-8"
    assert "auraspace_reservas.csv" in export_resp.headers["Content-Disposition"]
    assert export_resp.data.startswith(b"\xef\xbb\xbf")

    csv_text = export_resp.data.decode("utf-8")
    assert csv_text.startswith("\ufeff")
    # En texto crudo RFC 4180, las comillas internas se duplican dentro de campo entrecomillado
    assert '"Comité ""Q4"", diseño & café"' in csv_text
    assert '"Óscar Muñoz, Jr."' in csv_text
    assert '"Traer ""adaptador"", café y agua"' in csv_text

    rows = list(csv.reader(io.StringIO(csv_text.lstrip("\ufeff"))))
    assert len(rows) == 2
    headers, row = rows[0], rows[1]
    assert len(headers) == 15
    assert len(row) == 15
    assert row[0] == ref_code
    assert row[7] == special_title
    assert row[8] == special_customer
    assert row[13] == special_notes
