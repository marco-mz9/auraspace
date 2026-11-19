from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from models import Space

if TYPE_CHECKING:
    import sqlite3

    from database import DatabaseManager


class SpaceRepository:
    """Repositorio SQLite para gestionar la persistencia de salas de coworking."""

    def __init__(self, db: DatabaseManager) -> None:
        """Inicializa el repositorio con el gestor de base de datos."""
        self.db = db

    @staticmethod
    def _parse_bool(value: Any) -> bool:
        """Convierte valores booleanos, numéricos o textuales a booleano."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "si", "sí", "yes"}
        return bool(value)

    def list_all(self, filters: Mapping[str, Any] | None = None) -> list[Space]:
        """Lista las salas aplicando filtros opcionales de búsqueda y estado."""
        conditions: list[str] = []
        params: list[Any] = []

        if filters:
            q = str(filters.get("q") or "").strip()
            if q:
                like_term = f"%{q}%"
                conditions.append(
                    "(LOWER(name) LIKE LOWER(?) "
                    "OR LOWER(category) LIKE LOWER(?) "
                    "OR LOWER(equipment) LIKE LOWER(?))"
                )
                params.extend([like_term, like_term, like_term])

            category = str(filters.get("category") or "").strip()
            if category:
                conditions.append("LOWER(category) = LOWER(?)")
                params.append(category)

            min_capacity = filters.get("min_capacity")
            if min_capacity is not None and str(min_capacity).strip() != "":
                conditions.append("capacity >= ?")
                params.append(int(min_capacity))

            active_only = filters.get("active_only")
            if active_only is not None and self._parse_bool(active_only):
                conditions.append("is_active = 1")

        sql = "SELECT * FROM spaces"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY is_active DESC, name ASC;"

        conn = self.db.get_connection()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [Space.from_row(row) for row in rows]
        finally:
            conn.close()

    def get_by_id(
        self, space_id: int, conn: sqlite3.Connection | None = None
    ) -> Space | None:
        """Obtiene una sala por su identificador o None si no existe."""
        own_conn = conn is None
        active_conn = self.db.get_connection() if own_conn else conn
        assert active_conn is not None
        try:
            row = active_conn.execute(
                "SELECT * FROM spaces WHERE id = ?;",
                (space_id,),
            ).fetchone()
            return Space.from_row(row) if row is not None else None
        finally:
            if own_conn:
                active_conn.close()

    def create(
        self,
        name: str,
        category: str,
        floor: str,
        capacity: int,
        hourly_rate: float,
        equipment: str = "",
    ) -> Space:
        """Inserta una nueva sala activa y devuelve el modelo creado."""
        conn = self.db.get_connection()
        try:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO spaces (
                        name, category, floor, capacity, hourly_rate, equipment, is_active
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 1);
                    """,
                    (
                        name,
                        category,
                        floor,
                        int(capacity),
                        float(hourly_rate),
                        equipment,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM spaces WHERE id = ?;",
                    (cursor.lastrowid,),
                ).fetchone()
                assert row is not None
                return Space.from_row(row)
        finally:
            conn.close()

    def update_status(self, space_id: int, is_active: bool) -> Space | None:
        """Actualiza el estado activo/inactivo de una sala y la devuelve."""
        conn = self.db.get_connection()
        try:
            with conn:
                cursor = conn.execute(
                    "UPDATE spaces SET is_active = ? WHERE id = ?;",
                    (1 if is_active else 0, space_id),
                )
                if cursor.rowcount == 0:
                    return None
                row = conn.execute(
                    "SELECT * FROM spaces WHERE id = ?;",
                    (space_id,),
                ).fetchone()
                return Space.from_row(row) if row is not None else None
        finally:
            conn.close()
