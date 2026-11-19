from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    import sqlite3


@dataclass
class Space:
    """Representa una sala o espacio de coworking disponible para reservas."""

    name: str
    category: str
    floor: str
    capacity: int
    hourly_rate: float
    equipment: str = ""
    is_active: bool = True
    id: int | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializa la sala a un diccionario compatible con JSON."""
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "floor": self.floor,
            "capacity": int(self.capacity),
            "hourly_rate": round(float(self.hourly_rate), 2),
            "equipment": self.equipment,
            "is_active": bool(self.is_active),
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any] | sqlite3.Row) -> Self:
        """Construye una instancia de Space a partir de una fila de SQLite o mapeo."""
        return cls(
            id=row["id"],
            name=str(row["name"]),
            category=str(row["category"]),
            floor=str(row["floor"]),
            capacity=int(row["capacity"]),
            hourly_rate=float(row["hourly_rate"]),
            equipment=str(row["equipment"] or ""),
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
        )
