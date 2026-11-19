from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, ClassVar

from models import Booking

if TYPE_CHECKING:
    import sqlite3

    from database import DatabaseManager


class BookingRepository:
    """Repositorio SQLite para consultar y persistir reservas de salas."""

    _UPDATABLE_COLUMNS: ClassVar[tuple[str, ...]] = (
        "space_id",
        "title",
        "customer_name",
        "customer_email",
        "attendees",
        "booking_date",
        "start_time",
        "end_time",
        "total_price",
        "status",
        "notes",
    )

    def __init__(self, db: DatabaseManager) -> None:
        """Inicializa el repositorio con el gestor de base de datos."""
        self.db = db

    @classmethod
    def _extract_mapping(
        cls, booking_data: Booking | Mapping[str, Any]
    ) -> dict[str, Any]:
        """Normaliza un modelo Booking o diccionario a un mapeo plano."""
        if isinstance(booking_data, Booking):
            return {
                "reference_code": booking_data.reference_code,
                "space_id": booking_data.space_id,
                "title": booking_data.title,
                "customer_name": booking_data.customer_name,
                "customer_email": booking_data.customer_email,
                "attendees": booking_data.attendees,
                "booking_date": booking_data.booking_date,
                "start_time": booking_data.start_time,
                "end_time": booking_data.end_time,
                "total_price": booking_data.total_price,
                "status": booking_data.status,
                "notes": booking_data.notes,
            }
        return dict(booking_data)

    def list_filtered(
        self, filters: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Lista reservas enriquecidas con datos de su sala según filtros opcionales."""
        conditions: list[str] = []
        params: list[Any] = []

        if filters:
            q = str(filters.get("q") or "").strip()
            if q:
                like_term = f"%{q}%"
                conditions.append(
                    "(LOWER(b.reference_code) LIKE LOWER(?) "
                    "OR LOWER(b.title) LIKE LOWER(?) "
                    "OR LOWER(b.customer_name) LIKE LOWER(?) "
                    "OR LOWER(b.customer_email) LIKE LOWER(?) "
                    "OR LOWER(s.name) LIKE LOWER(?))"
                )
                params.extend([like_term] * 5)

            space_id = filters.get("space_id")
            if space_id is not None and str(space_id).strip() != "":
                conditions.append("b.space_id = ?")
                params.append(int(space_id))

            status = str(filters.get("status") or "").strip()
            if status:
                conditions.append("LOWER(b.status) = LOWER(?)")
                params.append(status)

            booking_date = str(
                filters.get("date") or filters.get("booking_date") or ""
            ).strip()
            if booking_date:
                conditions.append("b.booking_date = ?")
                params.append(booking_date)

        sql = (
            "SELECT b.*, s.name AS space_name, s.floor AS space_floor, "
            "s.category AS space_category, s.capacity AS space_capacity "
            "FROM bookings b "
            "INNER JOIN spaces s ON s.id = b.space_id"
        )
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY b.booking_date DESC, b.start_time ASC, b.id ASC;"

        conn = self.db.get_connection()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    **Booking.from_row(row).to_dict(),
                    "space_name": str(row["space_name"]),
                    "space_floor": str(row["space_floor"]),
                    "space_category": str(row["space_category"]),
                    "space_capacity": int(row["space_capacity"]),
                }
                for row in rows
            ]
        finally:
            conn.close()

    def get_by_id(
        self, booking_id: int, conn: sqlite3.Connection | None = None
    ) -> Booking | None:
        """Obtiene una reserva por su identificador o None si no existe."""
        own_conn = conn is None
        active_conn = self.db.get_connection() if own_conn else conn
        assert active_conn is not None
        try:
            row = active_conn.execute(
                "SELECT * FROM bookings WHERE id = ?;",
                (booking_id,),
            ).fetchone()
            return Booking.from_row(row) if row is not None else None
        finally:
            if own_conn:
                active_conn.close()

    def find_overlap(
        self,
        conn: sqlite3.Connection,
        space_id: int,
        booking_date: str,
        start_time: str,
        end_time: str,
        exclude_booking_id: int | None = None,
    ) -> Booking | None:
        """Busca una reserva no cancelada que se solape con la franja indicada."""
        sql = (
            "SELECT * FROM bookings "
            "WHERE space_id = ? "
            "AND booking_date = ? "
            "AND status != 'cancelada' "
            "AND start_time < ? "
            "AND end_time > ?"
        )
        params: list[Any] = [int(space_id), booking_date, end_time, start_time]

        if exclude_booking_id is not None:
            sql += " AND id != ?"
            params.append(int(exclude_booking_id))

        sql += " ORDER BY start_time ASC LIMIT 1;"
        row = conn.execute(sql, params).fetchone()
        return Booking.from_row(row) if row is not None else None

    def insert(
        self,
        conn: sqlite3.Connection,
        booking_data: Booking | Mapping[str, Any],
    ) -> Booking:
        """Inserta una reserva usando la conexión proporcionada y la devuelve."""
        data = self._extract_mapping(booking_data)
        notes = "" if data.get("notes") is None else str(data["notes"])
        status = str(data.get("status") or "confirmada")

        cursor = conn.execute(
            """
            INSERT INTO bookings (
                reference_code, space_id, title, customer_name, customer_email,
                attendees, booking_date, start_time, end_time, total_price,
                status, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                str(data["reference_code"]),
                int(data["space_id"]),
                str(data["title"]),
                str(data["customer_name"]),
                str(data["customer_email"]),
                int(data["attendees"]),
                str(data["booking_date"]),
                str(data["start_time"]),
                str(data["end_time"]),
                float(data["total_price"]),
                status,
                notes,
            ),
        )
        assert cursor.lastrowid is not None
        created = self.get_by_id(int(cursor.lastrowid), conn=conn)
        assert created is not None
        return created

    def update(
        self,
        conn: sqlite3.Connection,
        booking_id: int,
        booking_data: Booking | Mapping[str, Any],
    ) -> Booking | None:
        """Actualiza los campos editables de una reserva existente en la conexión dada."""
        data = self._extract_mapping(booking_data)
        columns: list[str] = []
        values: list[Any] = []

        for column in self._UPDATABLE_COLUMNS:
            if column not in data:
                continue
            value = data[column]
            if column in ("space_id", "attendees"):
                value = int(value)
            elif column == "total_price":
                value = float(value)
            elif column == "notes":
                value = "" if value is None else str(value)
            else:
                value = str(value)
            columns.append(column)
            values.append(value)

        if not columns:
            raise ValueError(
                "No se proporcionaron campos válidos para actualizar la reserva."
            )

        assignments = ", ".join(f"{column} = ?" for column in columns)
        values.append(int(booking_id))
        cursor = conn.execute(
            f"UPDATE bookings SET {assignments} WHERE id = ?;",
            values,
        )
        if cursor.rowcount == 0:
            return None
        return self.get_by_id(int(booking_id), conn=conn)

    def update_status(
        self,
        conn: sqlite3.Connection,
        booking_id: int,
        status: str,
        notes: str | None = None,
    ) -> Booking | None:
        """Actualiza el estado y opcionalmente las notas de una reserva existente."""
        if notes is None:
            cursor = conn.execute(
                "UPDATE bookings SET status = ? WHERE id = ?;",
                (status, int(booking_id)),
            )
        else:
            cursor = conn.execute(
                "UPDATE bookings SET status = ?, notes = ? WHERE id = ?;",
                (status, notes, int(booking_id)),
            )
        if cursor.rowcount == 0:
            return None
        return self.get_by_id(int(booking_id), conn=conn)
