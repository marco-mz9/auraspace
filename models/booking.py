from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Self, cast

if TYPE_CHECKING:
    import sqlite3

BookingStatus = Literal["confirmada", "completada", "cancelada"]


@dataclass
class Booking:
    """Representa una reserva de una sala de coworking en una fecha y franja horaria."""

    VALID_STATUSES: ClassVar[tuple[str, ...]] = (
        "confirmada",
        "completada",
        "cancelada",
    )

    space_id: int
    title: str
    customer_name: str
    customer_email: str
    attendees: int
    booking_date: str
    start_time: str
    end_time: str
    total_price: float = 0.0
    status: BookingStatus = "confirmada"
    notes: str = ""
    reference_code: str = ""
    id: int | None = None
    created_at: str | None = None

    @staticmethod
    def _parse_hhmm(value: str) -> datetime:
        """Valida y convierte una cadena con formato estricto HH:MM."""
        if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
            raise ValueError(
                f"Formato de hora inválido '{value}': debe ser HH:MM."
            )
        try:
            return datetime.strptime(value, "%H:%M")
        except ValueError as exc:
            raise ValueError(
                f"Hora inválida '{value}': debe cumplir el formato HH:MM."
            ) from exc

    def duration_hours(self) -> float:
        """Calcula la duración de la reserva en horas entre start_time y end_time."""
        start = self._parse_hhmm(self.start_time)
        end = self._parse_hhmm(self.end_time)
        minutes = (end - start).total_seconds() / 60
        if minutes <= 0:
            raise ValueError(
                "La hora de fin debe ser posterior a la hora de inicio."
            )
        return round(minutes / 60, 2)

    def to_dict(self) -> dict[str, Any]:
        """Serializa la reserva a un diccionario compatible con JSON."""
        return {
            "id": self.id,
            "reference_code": self.reference_code,
            "space_id": int(self.space_id),
            "title": self.title,
            "customer_name": self.customer_name,
            "customer_email": self.customer_email,
            "attendees": int(self.attendees),
            "booking_date": self.booking_date,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_hours": self.duration_hours(),
            "total_price": round(float(self.total_price), 2),
            "status": self.status,
            "notes": self.notes,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any] | sqlite3.Row) -> Self:
        """Construye una instancia de Booking a partir de una fila de SQLite o mapeo."""
        status_value = str(row["status"])
        if status_value not in cls.VALID_STATUSES:
            raise ValueError(f"Estado de reserva inválido: '{status_value}'.")
        return cls(
            id=row["id"],
            reference_code=str(row["reference_code"] or ""),
            space_id=int(row["space_id"]),
            title=str(row["title"]),
            customer_name=str(row["customer_name"]),
            customer_email=str(row["customer_email"]),
            attendees=int(row["attendees"]),
            booking_date=str(row["booking_date"]),
            start_time=str(row["start_time"]),
            end_time=str(row["end_time"]),
            total_price=float(row["total_price"]),
            status=cast("BookingStatus", status_value),
            notes=str(row["notes"] or ""),
            created_at=row["created_at"],
        )
