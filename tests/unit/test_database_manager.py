from __future__ import annotations

from pathlib import Path
import re
import sqlite3
from typing import Any

import pytest

from database import DatabaseManager

pytestmark = pytest.mark.unit


def _insert_sample_space(
    conn: sqlite3.Connection,
    name: str = "Sala Prueba DDL",
) -> int:
    """Inserta una sala válida para probar restricciones de bookings."""
    cursor = conn.execute(
        """
        INSERT INTO spaces (name, category, floor, capacity, hourly_rate, equipment, is_active)
        VALUES (?, 'Sala de reuniones', 'Planta 1', 8, 35.0, 'Wi-Fi', 1);
        """,
        (name,),
    )
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def _insert_sample_booking(
    conn: sqlite3.Connection,
    space_id: int,
    reference_code: str = "AURA-20261201-0001",
    **overrides: Any,
) -> int:
    """Inserta una reserva válida parametrizable para probar restricciones DDL."""
    data: dict[str, Any] = {
        "reference_code": reference_code,
        "space_id": space_id,
        "title": "Reunión DDL",
        "customer_name": "Elena Ruiz",
        "customer_email": "elena@empresa.es",
        "attendees": 4,
        "booking_date": "2026-12-01",
        "start_time": "10:00",
        "end_time": "12:00",
        "total_price": 70.0,
        "status": "confirmada",
        "notes": "",
    }
    data.update(overrides)
    cursor = conn.execute(
        """
        INSERT INTO bookings (
            reference_code, space_id, title, customer_name, customer_email,
            attendees, booking_date, start_time, end_time, total_price, status, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            data["reference_code"],
            data["space_id"],
            data["title"],
            data["customer_name"],
            data["customer_email"],
            data["attendees"],
            data["booking_date"],
            data["start_time"],
            data["end_time"],
            data["total_price"],
            data["status"],
            data["notes"],
        ),
    )
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def test_database_manager_memory_and_special_paths() -> None:
    """DatabaseManager soporta ':memory:' y rutas especiales sin crear carpetas espurias."""
    mem_db = DatabaseManager(":memory:")
    assert mem_db.db_path == ":memory:"

    conn = mem_db.get_connection()
    try:
        fk_row = conn.execute("PRAGMA foreign_keys;").fetchone()
        assert fk_row is not None
        assert int(fk_row[0]) == 1
        assert conn.row_factory is sqlite3.Row
    finally:
        conn.close()

    mem_db.init_schema()

    relative_db = DatabaseManager("local_only.db")
    assert relative_db.db_path == "local_only.db"

    uri_db = DatabaseManager("file:memdb_test?mode=memory&cache=shared")
    assert uri_db.db_path.startswith("file:")


def test_database_manager_creates_nested_parent_directories(tmp_path: Path) -> None:
    """Inicializar DatabaseManager con una ruta anidada crea los directorios padre."""
    nested_db_path = tmp_path / "nivel1" / "nivel2" / "auraspace.db"
    assert not nested_db_path.parent.exists()

    manager = DatabaseManager(nested_db_path)
    assert nested_db_path.parent.is_dir()
    assert manager.db_path == str(nested_db_path)


def test_get_connection_enables_foreign_keys_and_row_factory(
    db_manager: DatabaseManager,
) -> None:
    """get_connection activa PRAGMA foreign_keys = ON y row_factory = sqlite3.Row."""
    conn = db_manager.get_connection()
    try:
        fk_status = conn.execute("PRAGMA foreign_keys;").fetchone()
        assert fk_status is not None
        assert int(fk_status[0]) == 1
        assert conn.row_factory is sqlite3.Row
    finally:
        conn.close()


def test_init_schema_creates_tables_and_indexes_idempotently(
    db_manager: DatabaseManager,
) -> None:
    """init_schema crea tablas e índices esperados y puede ejecutarse varias veces."""
    db_manager.init_schema()

    conn = db_manager.get_connection()
    try:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table';"
            ).fetchall()
        }
        indexes = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index';"
            ).fetchall()
        }
        assert {"spaces", "bookings"}.issubset(tables)
        assert {
            "idx_bookings_space_date_status",
            "idx_bookings_date",
        }.issubset(indexes)
    finally:
        conn.close()


def test_seed_initial_data_is_idempotent_and_non_overlapping(
    db_manager: DatabaseManager,
) -> None:
    """seed_initial_data inserta 6 salas y 14 reservas AUR-* coherentes sin solapamientos."""
    assert db_manager.seed_initial_data() is True
    assert db_manager.seed_initial_data() is False

    conn = db_manager.get_connection()
    try:
        spaces = conn.execute("SELECT * FROM spaces ORDER BY id;").fetchall()
        bookings = conn.execute(
            """
            SELECT b.*, s.hourly_rate
            FROM bookings b
            INNER JOIN spaces s ON s.id = b.space_id
            ORDER BY b.id;
            """
        ).fetchall()

        assert len(spaces) == 6
        assert all(int(space["is_active"]) == 1 for space in spaces)
        assert len(bookings) == 14

        for b in bookings:
            assert re.fullmatch(r"AUR-\d{8}-\d{4}", b["reference_code"])
            expected_hours = DatabaseManager._hours_between(
                b["start_time"], b["end_time"]
            )
            assert float(b["total_price"]) == round(
                expected_hours * float(b["hourly_rate"]), 2
            )

        active = [b for b in bookings if b["status"] != "cancelada"]
        for i, first in enumerate(active):
            for second in active[i + 1 :]:
                if (
                    first["space_id"] == second["space_id"]
                    and first["booking_date"] == second["booking_date"]
                ):
                    overlaps = (
                        first["start_time"] < second["end_time"]
                        and first["end_time"] > second["start_time"]
                    )
                    assert not overlaps, (
                        f"Solapamiento en semilla entre {first['reference_code']} "
                        f"y {second['reference_code']}"
                    )
    finally:
        conn.close()


def test_seed_initial_data_skips_when_spaces_already_exist(
    db_manager: DatabaseManager,
) -> None:
    """seed_initial_data retorna False si la tabla spaces ya contiene algún registro."""
    conn = db_manager.get_connection()
    try:
        with conn:
            _insert_sample_space(conn, name="Sala Previa")
    finally:
        conn.close()

    assert db_manager.seed_initial_data() is False

    conn = db_manager.get_connection()
    try:
        total_spaces = conn.execute("SELECT COUNT(*) FROM spaces;").fetchone()[0]
        total_bookings = conn.execute("SELECT COUNT(*) FROM bookings;").fetchone()[0]
        assert total_spaces == 1
        assert total_bookings == 0
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("column", "bad_value"),
    [
        ("capacity", 0),
        ("capacity", -5),
        ("hourly_rate", 0.0),
        ("hourly_rate", -15.0),
        ("is_active", 2),
        ("is_active", -1),
    ],
)
def test_spaces_check_constraints_raise_integrity_error(
    db_manager: DatabaseManager, column: str, bad_value: Any
) -> None:
    """Los CHECK de la tabla spaces rechazan valores fuera de dominio."""
    values = {
        "name": f"Sala Inválida {column} {bad_value}",
        "category": "Sala de reuniones",
        "floor": "Planta 1",
        "capacity": 6,
        "hourly_rate": 30.0,
        "equipment": "",
        "is_active": 1,
    }
    values[column] = bad_value

    conn = db_manager.get_connection()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            with conn:
                conn.execute(
                    """
                    INSERT INTO spaces (
                        name, category, floor, capacity, hourly_rate, equipment, is_active
                    )
                    VALUES (:name, :category, :floor, :capacity, :hourly_rate, :equipment, :is_active);
                    """,
                    values,
                )
    finally:
        conn.close()


def test_spaces_unique_name_raises_integrity_error(
    db_manager: DatabaseManager,
) -> None:
    """UNIQUE(spaces.name) impide registrar dos salas con el mismo nombre."""
    conn = db_manager.get_connection()
    try:
        with conn:
            _insert_sample_space(conn, name="Sala Duplicada")
        with pytest.raises(sqlite3.IntegrityError):
            with conn:
                _insert_sample_space(conn, name="Sala Duplicada")
    finally:
        conn.close()


@pytest.mark.parametrize(
    "overrides",
    [
        {"attendees": 0},
        {"attendees": -2},
        {"total_price": -0.01},
        {"start_time": "10:00", "end_time": "10:00"},
        {"start_time": "12:00", "end_time": "11:00"},
        {"status": "pendiente"},
    ],
)
def test_bookings_check_constraints_raise_integrity_error(
    db_manager: DatabaseManager, overrides: dict[str, Any]
) -> None:
    """Los CHECK de la tabla bookings impiden asistentes, precios, horas y estados inválidos."""
    conn = db_manager.get_connection()
    try:
        with conn:
            space_id = _insert_sample_space(conn)
        with pytest.raises(sqlite3.IntegrityError):
            with conn:
                _insert_sample_booking(conn, space_id=space_id, **overrides)
    finally:
        conn.close()


def test_bookings_unique_reference_code_and_foreign_key_constraints(
    db_manager: DatabaseManager,
) -> None:
    """Valida UNIQUE(reference_code), FK space_id inexistente y ON DELETE RESTRICT."""
    conn = db_manager.get_connection()
    try:
        with conn:
            space_id = _insert_sample_space(conn, name="Sala Con Reserva")
            free_space_id = _insert_sample_space(conn, name="Sala Sin Reservas")
            _insert_sample_booking(
                conn, space_id=space_id, reference_code="AURA-20261201-UNIQ"
            )

        # Código de referencia duplicado
        with pytest.raises(sqlite3.IntegrityError):
            with conn:
                _insert_sample_booking(
                    conn,
                    space_id=space_id,
                    reference_code="AURA-20261201-UNIQ",
                    start_time="14:00",
                    end_time="15:00",
                )

        # Clave foránea space_id inexistente
        with pytest.raises(sqlite3.IntegrityError):
            with conn:
                _insert_sample_booking(
                    conn,
                    space_id=9999,
                    reference_code="AURA-20261201-NOFK",
                )

        # ON DELETE RESTRICT impide borrar una sala con reservas asociadas
        with pytest.raises(sqlite3.IntegrityError):
            with conn:
                conn.execute("DELETE FROM spaces WHERE id = ?;", (space_id,))

        # Una sala sin reservas sí puede eliminarse
        with conn:
            conn.execute("DELETE FROM spaces WHERE id = ?;", (free_space_id,))
        remaining = conn.execute(
            "SELECT COUNT(*) FROM spaces WHERE id = ?;", (free_space_id,)
        ).fetchone()[0]
        assert remaining == 0
    finally:
        conn.close()
