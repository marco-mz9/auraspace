from __future__ import annotations

from typing import Any

import pytest

from database import DatabaseManager
from repositories import BookingRepository, SpaceRepository
import services.reservation_service as reservation_service_module
from services import (
    ConflictError,
    DomainError,
    NotFoundError,
    ReservationService,
    ValidationError,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Excepciones de dominio
# ---------------------------------------------------------------------------


def test_domain_exceptions_hierarchy_and_status_codes() -> None:
    """Las excepciones de dominio heredan de DomainError y exponen su código HTTP."""
    domain_exc = DomainError("Error genérico")
    val_exc = ValidationError("Dato inválido")
    not_found_exc = NotFoundError("No encontrado")
    conflict_exc = ConflictError("Conflicto horario")

    assert domain_exc.status_code == 400
    assert str(domain_exc) == "Error genérico"

    assert isinstance(val_exc, DomainError)
    assert val_exc.status_code == 400
    assert str(val_exc) == "Dato inválido"

    assert isinstance(not_found_exc, DomainError)
    assert not_found_exc.status_code == 404
    assert str(not_found_exc) == "No encontrado"

    assert isinstance(conflict_exc, DomainError)
    assert conflict_exc.status_code == 409
    assert str(conflict_exc) == "Conflicto horario"


# ---------------------------------------------------------------------------
# Validadores de tipos primitivos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (1, 1),
        (42, 42),
        ("1", 1),
        (" 15 ", 15),
        ("+7", 7),
    ],
)
def test_parse_positive_int_valid(raw_value: Any, expected: int) -> None:
    """_parse_positive_int acepta enteros positivos y cadenas numéricas enteras."""
    assert ReservationService._parse_positive_int(raw_value, "campo") == expected


@pytest.mark.parametrize(
    "invalid_value",
    [
        0,
        -1,
        "-5",
        True,
        False,
        3.5,
        1.0,
        None,
        "",
        "   ",
        "abc",
        "3.5",
        [1],
    ],
)
def test_parse_positive_int_invalid_raises_validation_error(
    invalid_value: Any,
) -> None:
    """_parse_positive_int rechaza 0, negativos, bool, float, None y texto inválido."""
    with pytest.raises(ValidationError):
        ReservationService._parse_positive_int(invalid_value, "campo")


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (1, 1.0),
        (35.5, 35.5),
        (42.567, 42.57),
        (" 19.994 ", 19.99),
    ],
)
def test_parse_positive_float_valid(raw_value: Any, expected: float) -> None:
    """_parse_positive_float acepta positivos y redondea a 2 decimales."""
    assert ReservationService._parse_positive_float(raw_value, "tarifa") == expected


@pytest.mark.parametrize(
    "invalid_value",
    [
        0,
        0.0,
        -1,
        -0.01,
        True,
        False,
        None,
        "",
        "abc",
        "nan",
        "inf",
        "-inf",
        float("nan"),
        float("inf"),
        float("-inf"),
        [10],
    ],
)
def test_parse_positive_float_invalid_raises_validation_error(
    invalid_value: Any,
) -> None:
    """_parse_positive_float rechaza <=0, bool, None, texto y valores no finitos."""
    with pytest.raises(ValidationError):
        ReservationService._parse_positive_float(invalid_value, "tarifa")


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (True, True),
        (1, True),
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("si", True),
        ("sí", True),
        ("SÍ", True),
        ("yes", True),
        (" yes ", True),
        (False, False),
        (0, False),
        ("false", False),
        ("FALSE", False),
        ("0", False),
        ("no", False),
        (" NO ", False),
    ],
)
def test_parse_bool_flag_valid(raw_value: Any, expected: bool) -> None:
    """_parse_bool_flag interpreta booleanos, 0/1 y variantes textuales admitidas."""
    assert ReservationService._parse_bool_flag(raw_value, "is_active") is expected


@pytest.mark.parametrize(
    "invalid_value",
    [2, -1, 1.0, None, "", "quizas", "maybe", []],
)
def test_parse_bool_flag_invalid_raises_validation_error(
    invalid_value: Any,
) -> None:
    """_parse_bool_flag rechaza textos desconocidos y tipos inválidos."""
    with pytest.raises(ValidationError):
        ReservationService._parse_bool_flag(invalid_value, "is_active")


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    [
        ("Sala Aura", "Sala Aura"),
        ("  Sala Aura  ", "Sala Aura"),
    ],
)
def test_validate_required_text_valid(raw_text: str, expected: str) -> None:
    """_validate_required_text recorta espacios y devuelve el texto limpio."""
    assert ReservationService._validate_required_text(raw_text, "nombre") == expected


@pytest.mark.parametrize("invalid_text", [None, 123, "", "   "])
def test_validate_required_text_invalid_raises_validation_error(
    invalid_text: Any,
) -> None:
    """_validate_required_text rechaza no-strings y cadenas vacías o solo espacios."""
    with pytest.raises(ValidationError):
        ReservationService._validate_required_text(invalid_text, "nombre")


# ---------------------------------------------------------------------------
# Validadores de fecha, franja horaria y correo electrónico
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_date", "expected"),
    [
        ("2026-11-20", "2026-11-20"),
        (" 2024-02-29 ", "2024-02-29"),  # Año bisiesto válido
    ],
)
def test_validate_date_valid(raw_date: str, expected: str) -> None:
    """_validate_date valida fechas ISO reales y recorta espacios."""
    assert ReservationService._validate_date(raw_date) == expected


@pytest.mark.parametrize(
    "invalid_date",
    [
        None,
        20261120,
        "20-11-2026",
        "2026/11/20",
        "2026-1-5",
        "",
        "2026-02-30",
        "2025-02-29",  # Año no bisiesto
        "2026-13-01",
    ],
)
def test_validate_date_invalid_raises_validation_error(invalid_date: Any) -> None:
    """_validate_date rechaza formatos erróneos y fechas inexistentes en calendario."""
    with pytest.raises(ValidationError):
        ReservationService._validate_date(invalid_date)


@pytest.mark.parametrize(
    ("raw_time", "expected_clean", "expected_minutes"),
    [
        ("08:00", "08:00", 8 * 60),
        ("08:30", "08:30", 8 * 60 + 30),
        (" 15:30 ", "15:30", 15 * 60 + 30),
        ("21:00", "21:00", 21 * 60),
    ],
)
def test_parse_slot_time_valid(
    raw_time: str, expected_clean: str, expected_minutes: int
) -> None:
    """_parse_slot_time acepta fronteras exactas 08:00 y 21:00 y múltiplos de 30 min."""
    cleaned, total_minutes = ReservationService._parse_slot_time(raw_time, "inicio")
    assert cleaned == expected_clean
    assert total_minutes == expected_minutes


@pytest.mark.parametrize(
    "invalid_time",
    [
        "07:30",
        "21:30",
        "10:15",
        "09:45",
        "24:00",
        "12:60",
        "9:00",
        "ab:cd",
        "",
        None,
        900,
    ],
)
def test_parse_slot_time_invalid_raises_validation_error(
    invalid_time: Any,
) -> None:
    """_parse_slot_time rechaza fuera de horario, no múltiplos de 30, 24:00 y no-strings."""
    with pytest.raises(ValidationError):
        ReservationService._parse_slot_time(invalid_time, "inicio")


@pytest.mark.parametrize(
    ("raw_email", "expected"),
    [
        ("usuario@empresa.es", "usuario@empresa.es"),
        ("  nombre.apellido+qa@sub.dominio.com  ", "nombre.apellido+qa@sub.dominio.com"),
    ],
)
def test_validate_email_valid(raw_email: str, expected: str) -> None:
    """_validate_email valida direcciones válidas y recorta espacios laterales."""
    assert ReservationService._validate_email(raw_email) == expected


@pytest.mark.parametrize(
    "invalid_email",
    [
        None,
        123,
        "",
        "sin-arroba",
        "nombre@sin-tld",
        "@dominio.com",
        "nombre@.com",
        "con espacio@empresa.es",
    ],
)
def test_validate_email_invalid_raises_validation_error(invalid_email: Any) -> None:
    """_validate_email rechaza tipos inválidos y formatos de correo incorrectos."""
    with pytest.raises(ValidationError):
        ReservationService._validate_email(invalid_email)


# ---------------------------------------------------------------------------
# Validación integral de payload de reserva
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start_time", "end_time", "expected_hours", "notes_in", "notes_out"),
    [
        ("08:00", "08:30", 0.5, None, ""),
        ("08:00", "16:00", 8.0, "  Con proyector  ", "Con proyector"),
        ("13:00", "21:00", 8.0, "", ""),
    ],
)
def test_validate_booking_payload_boundaries_and_notes(
    start_time: str,
    end_time: str,
    expected_hours: float,
    notes_in: Any,
    notes_out: str,
) -> None:
    """_validate_booking_payload acepta duraciones límite (0.5h y 8.0h) y normaliza notes."""
    result = ReservationService._validate_booking_payload(
        {
            "space_id": "2",
            "title": "  Sesión estratégica  ",
            "customer_name": "  Laura Martín ",
            "customer_email": " laura@empresa.es ",
            "attendees": 4,
            "booking_date": " 2026-12-15 ",
            "start_time": start_time,
            "end_time": end_time,
            "notes": notes_in,
        }
    )
    assert result == {
        "space_id": 2,
        "title": "Sesión estratégica",
        "customer_name": "Laura Martín",
        "customer_email": "laura@empresa.es",
        "attendees": 4,
        "booking_date": "2026-12-15",
        "start_time": start_time,
        "end_time": end_time,
        "duration_hours": expected_hours,
        "notes": notes_out,
    }


@pytest.mark.parametrize(
    "bad_payload",
    [
        None,
        ["lista"],
        "texto",
    ],
)
def test_validate_booking_payload_non_mapping_raises_validation_error(
    bad_payload: Any,
) -> None:
    """_validate_booking_payload rechaza cuerpos que no son Mapping."""
    with pytest.raises(ValidationError):
        ReservationService._validate_booking_payload(bad_payload)


@pytest.mark.parametrize(
    "overrides",
    [
        {"start_time": "10:00", "end_time": "10:00"},
        {"start_time": "12:00", "end_time": "11:00"},
        {"start_time": "08:00", "end_time": "16:30"},  # > 8 horas
        {"title": "   "},
        {"customer_name": ""},
        {"customer_email": "invalido"},
        {"attendees": 0},
        {"space_id": -1},
        {"booking_date": "2026-02-30"},
    ],
)
def test_validate_booking_payload_invalid_rules_raise_validation_error(
    overrides: dict[str, Any],
) -> None:
    """_validate_booking_payload rechaza duraciones y campos fuera de regla."""
    payload: dict[str, Any] = {
        "space_id": 1,
        "title": "Reunión",
        "customer_name": "Carlos",
        "customer_email": "carlos@empresa.es",
        "attendees": 2,
        "booking_date": "2026-12-15",
        "start_time": "10:00",
        "end_time": "12:00",
    }
    payload.update(overrides)
    with pytest.raises(ValidationError):
        ReservationService._validate_booking_payload(payload)


# ---------------------------------------------------------------------------
# Generación de código de referencia y colisiones
# ---------------------------------------------------------------------------


def test_generate_reference_code_format_retry_and_exhaustion(
    db_manager: DatabaseManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_generate_reference_code genera AURA-YYYYMMDD-XXXX, reintenta y falla tras 30 colisiones."""
    space_repo = SpaceRepository(db_manager)
    booking_repo = BookingRepository(db_manager)
    service = ReservationService(db_manager, space_repo, booking_repo)

    space = space_repo.create(
        name="Sala Códigos",
        category="Sala de reuniones",
        floor="Planta 1",
        capacity=6,
        hourly_rate=30.0,
    )
    assert space.id is not None

    conn = db_manager.get_connection()
    try:
        # Formato válido normal
        generated = service._generate_reference_code(conn, "2026-12-15")
        assert generated.startswith("AURA-20261215-")
        assert len(generated) == len("AURA-20261215-XXXX")

        # Insertar código previo para forzar colisión
        with conn:
            booking_repo.insert(
                conn,
                {
                    "reference_code": "AURA-20261215-AAAA",
                    "space_id": space.id,
                    "title": "Reserva previa",
                    "customer_name": "Elena",
                    "customer_email": "elena@empresa.es",
                    "attendees": 2,
                    "booking_date": "2026-12-15",
                    "start_time": "10:00",
                    "end_time": "11:00",
                    "total_price": 30.0,
                    "status": "confirmada",
                    "notes": "",
                },
            )

        # Primer intento colisiona con AAAA y segundo intento genera BBBB
        sequence = iter(["A", "A", "A", "A", "B", "B", "B", "B"])
        monkeypatch.setattr(
            reservation_service_module.secrets,
            "choice",
            lambda _alphabet: next(sequence),
        )
        retried_code = service._generate_reference_code(conn, "2026-12-15")
        assert retried_code == "AURA-20261215-BBBB"

        # 30 colisiones consecutivas lanzan ConflictError
        calls = 0

        def always_a(_alphabet: str) -> str:
            nonlocal calls
            calls += 1
            return "A"

        monkeypatch.setattr(
            reservation_service_module.secrets,
            "choice",
            always_a,
        )
        with pytest.raises(ConflictError, match="código de reserva único"):
            service._generate_reference_code(conn, "2026-12-15")
        assert calls == 30 * 4
    finally:
        conn.close()
