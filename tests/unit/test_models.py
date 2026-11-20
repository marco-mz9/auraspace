from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from models import Booking, Space

pytestmark = pytest.mark.unit


def _make_sqlite_row(query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row:
    """Construye un sqlite3.Row real a partir de una consulta en memoria."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(query, params).fetchone()
        assert row is not None
        return row
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Pruebas del modelo Space
# ---------------------------------------------------------------------------


def test_space_creation_and_defaults() -> None:
    """Verifica valores por defecto y campos obligatorios al instanciar Space."""
    space = Space(
        name="Sala Ático",
        category="Sala de reuniones",
        floor="Planta 4",
        capacity=10,
        hourly_rate=45.0,
    )
    assert space.name == "Sala Ático"
    assert space.category == "Sala de reuniones"
    assert space.floor == "Planta 4"
    assert space.capacity == 10
    assert space.hourly_rate == 45.0
    assert space.equipment == ""
    assert space.is_active is True
    assert space.id is None
    assert space.created_at is None


@pytest.mark.parametrize(
    ("raw_rate", "expected_rate", "raw_active", "expected_active"),
    [
        (35.567, 35.57, True, True),
        (35.564, 35.56, 1, True),
        (40, 40.0, 0, False),
        (19.999, 20.0, False, False),
    ],
)
def test_space_to_dict_rounding_and_types(
    raw_rate: float,
    expected_rate: float,
    raw_active: Any,
    expected_active: bool,
) -> None:
    """to_dict redondea hourly_rate a 2 decimales y normaliza tipos."""
    space = Space(
        id=7,
        name="Sala Cuarzo",
        category="Oficina privada",
        floor="Planta 2",
        capacity="6",  # type: ignore[arg-type]
        hourly_rate=raw_rate,
        equipment="Monitor 4K, Wi-Fi 6",
        is_active=raw_active,
        created_at="2026-11-20 09:00:00",
    )
    data = space.to_dict()
    assert data == {
        "id": 7,
        "name": "Sala Cuarzo",
        "category": "Oficina privada",
        "floor": "Planta 2",
        "capacity": 6,
        "hourly_rate": expected_rate,
        "equipment": "Monitor 4K, Wi-Fi 6",
        "is_active": expected_active,
        "created_at": "2026-11-20 09:00:00",
    }
    assert isinstance(data["capacity"], int)
    assert isinstance(data["is_active"], bool)


def test_space_from_row_with_sqlite_row_and_none_equipment() -> None:
    """from_row construye Space desde sqlite3.Row y normaliza equipment=None a ''."""
    row = _make_sqlite_row(
        """
        SELECT
            3 AS id,
            'Cabina Focus B' AS name,
            'Cabina individual' AS category,
            'Planta 1' AS floor,
            2 AS capacity,
            15.5 AS hourly_rate,
            NULL AS equipment,
            0 AS is_active,
            '2026-11-20 10:00:00' AS created_at
        """
    )
    space = Space.from_row(row)
    assert space.id == 3
    assert space.name == "Cabina Focus B"
    assert space.category == "Cabina individual"
    assert space.floor == "Planta 1"
    assert space.capacity == 2
    assert space.hourly_rate == 15.5
    assert space.equipment == ""
    assert space.is_active is False
    assert space.created_at == "2026-11-20 10:00:00"


# ---------------------------------------------------------------------------
# Pruebas del modelo Booking
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("hhmm", "expected_hour", "expected_minute"),
    [
        ("00:00", 0, 0),
        ("08:30", 8, 30),
        ("12:00", 12, 0),
        ("23:59", 23, 59),
    ],
)
def test_booking_parse_hhmm_valid(
    hhmm: str, expected_hour: int, expected_minute: int
) -> None:
    """_parse_hhmm acepta horas válidas con formato estricto HH:MM."""
    parsed = Booking._parse_hhmm(hhmm)
    assert parsed.hour == expected_hour
    assert parsed.minute == expected_minute


@pytest.mark.parametrize(
    "invalid_value",
    [
        "9:00",
        "09:0",
        "09:000",
        "",
        "09-00",
        "09.30",
        "0900",
        "24:00",
        "25:30",
        "10:60",
        "ab:cd",
        None,
        900,
    ],
)
def test_booking_parse_hhmm_invalid_raises_value_error(invalid_value: Any) -> None:
    """_parse_hhmm rechaza longitud incorrecta, separador erróneo o horas imposibles."""
    with pytest.raises(ValueError):
        Booking._parse_hhmm(invalid_value)


@pytest.mark.parametrize(
    ("start_time", "end_time", "expected_hours"),
    [
        ("08:00", "08:30", 0.5),
        ("10:00", "12:30", 2.5),
        ("08:00", "16:00", 8.0),
        ("09:00", "09:20", 0.33),
    ],
)
def test_booking_duration_hours_valid(
    start_time: str, end_time: str, expected_hours: float
) -> None:
    """duration_hours calcula y redondea correctamente la duración en horas."""
    booking = Booking(
        space_id=1,
        title="Sesión",
        customer_name="Ana Pérez",
        customer_email="ana@empresa.es",
        attendees=3,
        booking_date="2026-12-01",
        start_time=start_time,
        end_time=end_time,
    )
    assert booking.duration_hours() == expected_hours


@pytest.mark.parametrize(
    ("start_time", "end_time"),
    [
        ("10:00", "10:00"),
        ("14:00", "12:00"),
    ],
)
def test_booking_duration_hours_non_positive_raises_value_error(
    start_time: str, end_time: str
) -> None:
    """duration_hours lanza ValueError si la hora de fin es menor o igual al inicio."""
    booking = Booking(
        space_id=1,
        title="Sesión inválida",
        customer_name="Ana Pérez",
        customer_email="ana@empresa.es",
        attendees=2,
        booking_date="2026-12-01",
        start_time=start_time,
        end_time=end_time,
    )
    with pytest.raises(ValueError, match="posterior"):
        booking.duration_hours()


def test_booking_to_dict_serializes_fields_and_rounds_price() -> None:
    """to_dict incluye duración calculada, precio redondeado y todos los atributos."""
    booking = Booking(
        id=15,
        reference_code="AURA-20261201-AB12",
        space_id="2",  # type: ignore[arg-type]
        title="Comité técnico",
        customer_name="Luis Gómez",
        customer_email="luis@empresa.es",
        attendees="5",  # type: ignore[arg-type]
        booking_date="2026-12-01",
        start_time="09:00",
        end_time="11:30",
        total_price=125.556,
        status="confirmada",
        notes="Con proyector",
        created_at="2026-11-20 11:00:00",
    )
    data = booking.to_dict()
    assert data == {
        "id": 15,
        "reference_code": "AURA-20261201-AB12",
        "space_id": 2,
        "title": "Comité técnico",
        "customer_name": "Luis Gómez",
        "customer_email": "luis@empresa.es",
        "attendees": 5,
        "booking_date": "2026-12-01",
        "start_time": "09:00",
        "end_time": "11:30",
        "duration_hours": 2.5,
        "total_price": 125.56,
        "status": "confirmada",
        "notes": "Con proyector",
        "created_at": "2026-11-20 11:00:00",
    }
    assert isinstance(data["space_id"], int)
    assert isinstance(data["attendees"], int)


@pytest.mark.parametrize("status", ["confirmada", "completada", "cancelada"])
def test_booking_from_row_valid_statuses_and_none_notes(status: str) -> None:
    """from_row construye Booking desde sqlite3.Row y normaliza notes/reference_code None."""
    row = _make_sqlite_row(
        """
        SELECT
            9 AS id,
            NULL AS reference_code,
            4 AS space_id,
            'Taller UX' AS title,
            'María López' AS customer_name,
            'maria@empresa.es' AS customer_email,
            6 AS attendees,
            '2026-12-10' AS booking_date,
            '10:00' AS start_time,
            '12:00' AS end_time,
            84.0 AS total_price,
            ? AS status,
            NULL AS notes,
            '2026-11-20 11:15:00' AS created_at
        """,
        (status,),
    )
    booking = Booking.from_row(row)
    assert booking.id == 9
    assert booking.reference_code == ""
    assert booking.space_id == 4
    assert booking.attendees == 6
    assert booking.status == status
    assert booking.notes == ""
    assert booking.total_price == 84.0
    assert booking.duration_hours() == 2.0


@pytest.mark.parametrize("bad_status", ["pendiente", "CONFIRMADA", "", "borrada"])
def test_booking_from_row_invalid_status_raises_value_error(bad_status: str) -> None:
    """from_row rechaza estados fuera de Booking.VALID_STATUSES."""
    row = _make_sqlite_row(
        """
        SELECT
            1 AS id,
            'AURA-20261210-0001' AS reference_code,
            1 AS space_id,
            'Taller' AS title,
            'María' AS customer_name,
            'maria@empresa.es' AS customer_email,
            2 AS attendees,
            '2026-12-10' AS booking_date,
            '10:00' AS start_time,
            '11:00' AS end_time,
            35.0 AS total_price,
            ? AS status,
            '' AS notes,
            '2026-11-20 11:15:00' AS created_at
        """,
        (bad_status,),
    )
    with pytest.raises(ValueError, match="Estado de reserva inválido"):
        Booking.from_row(row)
