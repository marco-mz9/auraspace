from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
import csv
from datetime import date
import io
import math
import re
import secrets
import sqlite3
import string
from typing import TYPE_CHECKING, Any

from models import Booking

if TYPE_CHECKING:
    from database import DatabaseManager
    from models import Space
    from repositories import BookingRepository, SpaceRepository


class DomainError(Exception):
    """Excepción base de errores de negocio mapeable a códigos HTTP."""

    status_code: int = 400


class ValidationError(DomainError):
    """Error de validación de datos de entrada o reglas de negocio."""

    status_code: int = 400


class NotFoundError(DomainError):
    """Error cuando el recurso solicitado no existe."""

    status_code: int = 404


class ConflictError(DomainError):
    """Error de conflicto por solapamiento horario o duplicidad."""

    status_code: int = 409


class ReservationService:
    """Orquesta las reglas de negocio, transacciones y analítica de reservas."""

    OPEN_MINUTES: int = 8 * 60
    CLOSE_MINUTES: int = 21 * 60
    SLOT_MINUTES: int = 30
    MIN_DURATION_MINUTES: int = 30
    MAX_DURATION_MINUTES: int = 8 * 60

    _DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    _TIME_RE = re.compile(r"^\d{2}:\d{2}$")
    _EMAIL_RE = re.compile(
        r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$"
    )
    _REF_ALPHABET = string.ascii_uppercase + string.digits

    def __init__(
        self,
        db: DatabaseManager,
        space_repo: SpaceRepository,
        booking_repo: BookingRepository,
    ) -> None:
        """Inicializa el servicio con el gestor de BD y los repositorios."""
        self.db = db
        self.space_repo = space_repo
        self.booking_repo = booking_repo

    @contextmanager
    def _immediate_transaction(self) -> Iterator[sqlite3.Connection]:
        """Abre una transacción SQLite BEGIN IMMEDIATE con commit/rollback explícitos."""
        conn = self.db.get_connection(isolation_level=None)
        try:
            conn.execute("BEGIN IMMEDIATE;")
            yield conn
            if conn.in_transaction:
                conn.execute("COMMIT;")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

    @staticmethod
    def _parse_positive_int(value: Any, field_label: str) -> int:
        """Valida y convierte un valor en entero estrictamente positivo."""
        if isinstance(value, (bool, float)) or value is None:
            raise ValidationError(
                f"El campo '{field_label}' debe ser un número entero mayor que 0."
            )
        if isinstance(value, int):
            parsed = value
        elif isinstance(value, str):
            text = value.strip()
            if not text or not re.fullmatch(r"[+-]?\d+", text):
                raise ValidationError(
                    f"El campo '{field_label}' debe ser un número entero válido."
                )
            parsed = int(text)
        else:
            raise ValidationError(
                f"El campo '{field_label}' debe ser un número entero válido."
            )

        if parsed <= 0:
            raise ValidationError(
                f"El campo '{field_label}' debe ser mayor que 0."
            )
        return parsed

    @staticmethod
    def _parse_positive_float(value: Any, field_label: str) -> float:
        """Valida y convierte un valor en número decimal estrictamente positivo."""
        if isinstance(value, bool) or value is None:
            raise ValidationError(
                f"El campo '{field_label}' debe ser un número mayor que 0."
            )
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                f"El campo '{field_label}' debe ser un número válido."
            ) from exc

        if not math.isfinite(parsed) or parsed <= 0:
            raise ValidationError(
                f"El campo '{field_label}' debe ser mayor que 0."
            )
        return round(parsed, 2)

    @staticmethod
    def _parse_bool_flag(value: Any, field_label: str) -> bool:
        """Valida y convierte un indicador booleano explícito."""
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "si", "sí", "yes"}:
                return True
            if normalized in {"false", "0", "no"}:
                return False
        raise ValidationError(
            f"El campo '{field_label}' debe ser un valor booleano válido."
        )

    @staticmethod
    def _validate_required_text(value: Any, field_label: str) -> str:
        """Valida que un campo de texto obligatorio no esté vacío."""
        if not isinstance(value, str):
            raise ValidationError(f"El campo '{field_label}' es obligatorio.")
        cleaned = value.strip()
        if not cleaned:
            raise ValidationError(
                f"El campo '{field_label}' no puede estar vacío."
            )
        return cleaned

    @classmethod
    def _validate_date(cls, value: Any) -> str:
        """Valida que la fecha tenga formato YYYY-MM-DD y exista en el calendario."""
        if not isinstance(value, str):
            raise ValidationError(
                "La fecha debe tener el formato válido YYYY-MM-DD."
            )
        cleaned = value.strip()
        if not cls._DATE_RE.match(cleaned):
            raise ValidationError(
                f"Formato de fecha inválido '{cleaned}': use YYYY-MM-DD."
            )
        try:
            date.fromisoformat(cleaned)
        except ValueError as exc:
            raise ValidationError(
                f"La fecha '{cleaned}' no existe en el calendario."
            ) from exc
        return cleaned

    @classmethod
    def _parse_slot_time(cls, value: Any, field_label: str) -> tuple[str, int]:
        """Valida una hora HH:MM múltiplo de 30 min dentro de 08:00-21:00."""
        if not isinstance(value, str):
            raise ValidationError(
                f"La hora de {field_label} debe tener formato HH:MM."
            )
        cleaned = value.strip()
        if not cls._TIME_RE.match(cleaned):
            raise ValidationError(
                f"Formato inválido para hora de {field_label} '{cleaned}': use HH:MM."
            )

        hour_str, minute_str = cleaned.split(":")
        hour = int(hour_str)
        minute = int(minute_str)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValidationError(
                f"Hora fuera de rango para {field_label}: '{cleaned}'."
            )

        total_minutes = hour * 60 + minute
        if total_minutes % cls.SLOT_MINUTES != 0:
            raise ValidationError(
                f"La hora de {field_label} '{cleaned}' debe ser múltiplo de 30 minutos (:00 o :30)."
            )
        if not (cls.OPEN_MINUTES <= total_minutes <= cls.CLOSE_MINUTES):
            raise ValidationError(
                f"La hora de {field_label} '{cleaned}' debe estar dentro del horario comercial (08:00 a 21:00)."
            )
        return cleaned, total_minutes

    @classmethod
    def _validate_email(cls, value: Any) -> str:
        """Valida el formato del correo electrónico mediante expresión regular."""
        if not isinstance(value, str):
            raise ValidationError("El correo electrónico es obligatorio.")
        cleaned = value.strip()
        if not cls._EMAIL_RE.match(cleaned):
            raise ValidationError(
                f"El correo electrónico '{cleaned}' no tiene un formato válido."
            )
        return cleaned

    @staticmethod
    def _minutes_to_hhmm(total_minutes: int) -> str:
        """Convierte minutos desde medianoche a cadena HH:MM."""
        hour, minute = divmod(total_minutes, 60)
        return f"{hour:02d}:{minute:02d}"

    @staticmethod
    def _hhmm_to_minutes(hhmm: str) -> int:
        """Convierte una hora HH:MM a minutos desde medianoche."""
        hour, minute = map(int, hhmm.split(":"))
        return hour * 60 + minute

    @classmethod
    def _validate_booking_payload(
        cls, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Valida y normaliza todos los campos requeridos para una reserva."""
        if not isinstance(payload, Mapping):
            raise ValidationError("El cuerpo de la solicitud debe ser un objeto JSON.")

        space_id = cls._parse_positive_int(payload.get("space_id"), "space_id")
        title = cls._validate_required_text(payload.get("title"), "título")
        customer_name = cls._validate_required_text(
            payload.get("customer_name"), "nombre del cliente"
        )
        customer_email = cls._validate_email(payload.get("customer_email"))
        attendees = cls._parse_positive_int(
            payload.get("attendees"), "asistentes"
        )
        booking_date = cls._validate_date(payload.get("booking_date"))
        start_time, start_minutes = cls._parse_slot_time(
            payload.get("start_time"), "inicio"
        )
        end_time, end_minutes = cls._parse_slot_time(
            payload.get("end_time"), "fin"
        )

        duration_minutes = end_minutes - start_minutes
        if duration_minutes <= 0:
            raise ValidationError(
                "La hora de fin debe ser posterior a la hora de inicio."
            )
        if duration_minutes < cls.MIN_DURATION_MINUTES:
            raise ValidationError(
                "La duración mínima de una reserva es de 30 minutos."
            )
        if duration_minutes > cls.MAX_DURATION_MINUTES:
            raise ValidationError(
                "La duración máxima de una reserva es de 8 horas."
            )

        raw_notes = payload.get("notes")
        notes = "" if raw_notes is None else str(raw_notes).strip()

        return {
            "space_id": space_id,
            "title": title,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "attendees": attendees,
            "booking_date": booking_date,
            "start_time": start_time,
            "end_time": end_time,
            "duration_hours": round(duration_minutes / 60, 2),
            "notes": notes,
        }

    def _generate_reference_code(
        self, conn: sqlite3.Connection, booking_date: str
    ) -> str:
        """Genera un código de referencia único con formato AURA-YYYYMMDD-XXXX."""
        compact_date = booking_date.replace("-", "")
        for _ in range(30):
            suffix = "".join(
                secrets.choice(self._REF_ALPHABET) for _ in range(4)
            )
            code = f"AURA-{compact_date}-{suffix}"
            exists = conn.execute(
                "SELECT 1 FROM bookings WHERE reference_code = ?;",
                (code,),
            ).fetchone()
            if exists is None:
                return code
        raise ConflictError(
            "No fue posible generar un código de reserva único."
        )

    @staticmethod
    def _enrich_booking(booking: Booking, space: Space) -> dict[str, Any]:
        """Combina los datos de una reserva con la información de su sala."""
        return {
            **booking.to_dict(),
            "space_name": space.name,
            "space_floor": space.floor,
            "space_category": space.category,
            "space_capacity": int(space.capacity),
        }

    def list_spaces(
        self, filters: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Lista las salas filtradas en formato serializable."""
        return [space.to_dict() for space in self.space_repo.list_all(filters)]

    def get_space(self, space_id: int) -> dict[str, Any]:
        """Obtiene una sala por su identificador o lanza NotFoundError."""
        parsed_id = self._parse_positive_int(space_id, "space_id")
        space = self.space_repo.get_by_id(parsed_id)
        if space is None:
            raise NotFoundError(f"No existe la sala con id {parsed_id}.")
        return space.to_dict()

    def create_space(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Valida y crea una nueva sala de coworking."""
        if not isinstance(payload, Mapping):
            raise ValidationError("El cuerpo de la solicitud debe ser un objeto JSON.")

        name = self._validate_required_text(payload.get("name"), "nombre")
        category = self._validate_required_text(
            payload.get("category"), "categoría"
        )
        floor = self._validate_required_text(payload.get("floor"), "planta")
        capacity = self._parse_positive_int(
            payload.get("capacity"), "capacidad"
        )
        hourly_rate = self._parse_positive_float(
            payload.get("hourly_rate"), "tarifa por hora"
        )
        raw_equipment = payload.get("equipment")
        equipment = "" if raw_equipment is None else str(raw_equipment).strip()

        try:
            space = self.space_repo.create(
                name=name,
                category=category,
                floor=floor,
                capacity=capacity,
                hourly_rate=hourly_rate,
                equipment=equipment,
            )
        except sqlite3.IntegrityError as exc:
            raise ConflictError(
                f"Ya existe una sala registrada con el nombre '{name}'."
            ) from exc
        return space.to_dict()

    def update_space_status(
        self, space_id: int, is_active: Any
    ) -> dict[str, Any]:
        """Activa o desactiva una sala existente."""
        parsed_id = self._parse_positive_int(space_id, "space_id")
        active_flag = self._parse_bool_flag(is_active, "is_active")
        updated = self.space_repo.update_status(parsed_id, active_flag)
        if updated is None:
            raise NotFoundError(f"No existe la sala con id {parsed_id}.")
        return updated.to_dict()

    def list_bookings(
        self, filters: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Lista las reservas aplicando los filtros indicados."""
        return self.booking_repo.list_filtered(filters)

    def get_booking(self, booking_id: int) -> dict[str, Any]:
        """Obtiene una reserva enriquecida por su identificador."""
        parsed_id = self._parse_positive_int(booking_id, "booking_id")
        booking = self.booking_repo.get_by_id(parsed_id)
        if booking is None:
            raise NotFoundError(f"No existe la reserva con id {parsed_id}.")
        space = self.space_repo.get_by_id(booking.space_id)
        if space is None:
            raise NotFoundError(
                f"No existe la sala asociada con id {booking.space_id}."
            )
        return self._enrich_booking(booking, space)

    def create_booking(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Crea una reserva tras validar reglas de negocio bajo BEGIN IMMEDIATE."""
        validated = self._validate_booking_payload(payload)

        with self._immediate_transaction() as conn:
            space = self.space_repo.get_by_id(validated["space_id"], conn=conn)
            if space is None:
                raise NotFoundError(
                    f"No existe la sala con id {validated['space_id']}."
                )
            if not space.is_active:
                raise ValidationError(
                    f"La sala '{space.name}' está inactiva y no admite reservas."
                )
            if validated["attendees"] > space.capacity:
                raise ValidationError(
                    f"El número de asistentes ({validated['attendees']}) supera "
                    f"el aforo máximo de '{space.name}' ({space.capacity})."
                )

            overlap = self.booking_repo.find_overlap(
                conn=conn,
                space_id=validated["space_id"],
                booking_date=validated["booking_date"],
                start_time=validated["start_time"],
                end_time=validated["end_time"],
            )
            if overlap is not None:
                raise ConflictError(
                    f"La sala '{space.name}' ya está reservada entre "
                    f"{overlap.start_time} y {overlap.end_time} "
                    f"(código {overlap.reference_code})."
                )

            total_price = round(
                validated["duration_hours"] * space.hourly_rate, 2
            )
            reference_code = self._generate_reference_code(
                conn, validated["booking_date"]
            )

            created = self.booking_repo.insert(
                conn,
                {
                    "reference_code": reference_code,
                    "space_id": validated["space_id"],
                    "title": validated["title"],
                    "customer_name": validated["customer_name"],
                    "customer_email": validated["customer_email"],
                    "attendees": validated["attendees"],
                    "booking_date": validated["booking_date"],
                    "start_time": validated["start_time"],
                    "end_time": validated["end_time"],
                    "total_price": total_price,
                    "status": "confirmada",
                    "notes": validated["notes"],
                },
            )
            return self._enrich_booking(created, space)

    def update_booking(
        self, booking_id: int, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Actualiza una reserva activa validando disponibilidad bajo BEGIN IMMEDIATE."""
        parsed_id = self._parse_positive_int(booking_id, "booking_id")
        if not isinstance(payload, Mapping):
            raise ValidationError("El cuerpo de la solicitud debe ser un objeto JSON.")

        with self._immediate_transaction() as conn:
            existing = self.booking_repo.get_by_id(parsed_id, conn=conn)
            if existing is None:
                raise NotFoundError(
                    f"No existe la reserva con id {parsed_id}."
                )
            if existing.status == "cancelada":
                raise ValidationError(
                    "No se puede editar una reserva que ya fue cancelada."
                )

            merged: dict[str, Any] = {
                "space_id": payload.get("space_id", existing.space_id),
                "title": payload.get("title", existing.title),
                "customer_name": payload.get(
                    "customer_name", existing.customer_name
                ),
                "customer_email": payload.get(
                    "customer_email", existing.customer_email
                ),
                "attendees": payload.get("attendees", existing.attendees),
                "booking_date": payload.get(
                    "booking_date", existing.booking_date
                ),
                "start_time": payload.get("start_time", existing.start_time),
                "end_time": payload.get("end_time", existing.end_time),
                "notes": payload.get("notes", existing.notes),
            }
            validated = self._validate_booking_payload(merged)

            space = self.space_repo.get_by_id(validated["space_id"], conn=conn)
            if space is None:
                raise NotFoundError(
                    f"No existe la sala con id {validated['space_id']}."
                )
            if not space.is_active:
                raise ValidationError(
                    f"La sala '{space.name}' está inactiva y no admite reservas."
                )
            if validated["attendees"] > space.capacity:
                raise ValidationError(
                    f"El número de asistentes ({validated['attendees']}) supera "
                    f"el aforo máximo de '{space.name}' ({space.capacity})."
                )

            overlap = self.booking_repo.find_overlap(
                conn=conn,
                space_id=validated["space_id"],
                booking_date=validated["booking_date"],
                start_time=validated["start_time"],
                end_time=validated["end_time"],
                exclude_booking_id=parsed_id,
            )
            if overlap is not None:
                raise ConflictError(
                    f"La sala '{space.name}' ya tiene una reserva solapada entre "
                    f"{overlap.start_time} y {overlap.end_time} "
                    f"(código {overlap.reference_code})."
                )

            total_price = round(
                validated["duration_hours"] * space.hourly_rate, 2
            )

            updated = self.booking_repo.update(
                conn,
                parsed_id,
                {
                    "space_id": validated["space_id"],
                    "title": validated["title"],
                    "customer_name": validated["customer_name"],
                    "customer_email": validated["customer_email"],
                    "attendees": validated["attendees"],
                    "booking_date": validated["booking_date"],
                    "start_time": validated["start_time"],
                    "end_time": validated["end_time"],
                    "total_price": total_price,
                    "notes": validated["notes"],
                },
            )
            assert updated is not None
            return self._enrich_booking(updated, space)

    def change_status(
        self, booking_id: int, status: str, notes: str | None = None
    ) -> dict[str, Any]:
        """Cambia el estado de una reserva validando reactivaciones bajo BEGIN IMMEDIATE."""
        parsed_id = self._parse_positive_int(booking_id, "booking_id")
        if not isinstance(status, str):
            raise ValidationError("El estado de la reserva es obligatorio.")
        normalized_status = status.strip().lower()
        if normalized_status not in Booking.VALID_STATUSES:
            allowed = ", ".join(Booking.VALID_STATUSES)
            raise ValidationError(
                f"Estado '{status}' no válido. Valores permitidos: {allowed}."
            )

        cleaned_notes = None if notes is None else str(notes).strip()

        with self._immediate_transaction() as conn:
            existing = self.booking_repo.get_by_id(parsed_id, conn=conn)
            if existing is None:
                raise NotFoundError(
                    f"No existe la reserva con id {parsed_id}."
                )

            space = self.space_repo.get_by_id(existing.space_id, conn=conn)
            if space is None:
                raise NotFoundError(
                    f"No existe la sala con id {existing.space_id}."
                )

            if (
                existing.status == "cancelada"
                and normalized_status != "cancelada"
            ):
                if not space.is_active:
                    raise ValidationError(
                        f"No se puede reactivar la reserva porque la sala '{space.name}' está inactiva."
                    )
                overlap = self.booking_repo.find_overlap(
                    conn=conn,
                    space_id=existing.space_id,
                    booking_date=existing.booking_date,
                    start_time=existing.start_time,
                    end_time=existing.end_time,
                    exclude_booking_id=parsed_id,
                )
                if overlap is not None:
                    raise ConflictError(
                        f"No se puede reactivar la reserva: la franja "
                        f"{existing.start_time}-{existing.end_time} ya fue ocupada "
                        f"por {overlap.reference_code}."
                    )

            updated = self.booking_repo.update_status(
                conn, parsed_id, normalized_status, notes=cleaned_notes
            )
            assert updated is not None
            return self._enrich_booking(updated, space)

    def get_availability(
        self,
        space_id: int,
        booking_date: str,
        exclude_booking_id: int | None = None,
    ) -> dict[str, Any]:
        """Devuelve los 26 bloques de 30 minutos (08:00-21:00) y su disponibilidad."""
        parsed_space_id = self._parse_positive_int(space_id, "space_id")
        valid_date = self._validate_date(booking_date)
        parsed_exclude_id = (
            self._parse_positive_int(exclude_booking_id, "exclude_booking_id")
            if exclude_booking_id is not None
            else None
        )

        space = self.space_repo.get_by_id(parsed_space_id)
        if space is None:
            raise NotFoundError(f"No existe la sala con id {parsed_space_id}.")

        bookings = self.booking_repo.list_filtered(
            {"space_id": parsed_space_id, "date": valid_date}
        )
        active_bookings = [
            b
            for b in bookings
            if b["status"] != "cancelada"
            and (parsed_exclude_id is None or b["id"] != parsed_exclude_id)
        ]

        parsed_ranges = [
            (
                self._hhmm_to_minutes(b["start_time"]),
                self._hhmm_to_minutes(b["end_time"]),
                b,
            )
            for b in active_bookings
        ]

        slots: list[dict[str, Any]] = []
        for slot_start_min in range(
            self.OPEN_MINUTES, self.CLOSE_MINUTES, self.SLOT_MINUTES
        ):
            slot_end_min = slot_start_min + self.SLOT_MINUTES
            occupying: dict[str, Any] | None = None
            for b_start, b_end, booking_item in parsed_ranges:
                if b_start < slot_end_min and b_end > slot_start_min:
                    occupying = booking_item
                    break

            is_available = space.is_active and occupying is None
            slot_title = (
                occupying["title"]
                if occupying
                else (None if space.is_active else "Sala en mantenimiento")
            )
            slot_status = (
                occupying["status"]
                if occupying
                else (None if space.is_active else "mantenimiento")
            )

            slots.append(
                {
                    "start_time": self._minutes_to_hhmm(slot_start_min),
                    "end_time": self._minutes_to_hhmm(slot_end_min),
                    "available": is_available,
                    "occupied": not is_available,
                    "booking_id": occupying["id"] if occupying else None,
                    "reference_code": (
                        occupying["reference_code"] if occupying else None
                    ),
                    "title": slot_title,
                    "status": slot_status,
                }
            )

        available_count = sum(1 for slot in slots if slot["available"])
        return {
            "space": space.to_dict(),
            "booking_date": valid_date,
            "total_slots": len(slots),
            "available_slots": available_count,
            "occupied_slots": len(slots) - available_count,
            "slots": slots,
        }

    def get_daily_schedule(self, booking_date: str) -> dict[str, Any]:
        """Devuelve todas las salas con sus reservas activas para la fecha indicada."""
        valid_date = self._validate_date(booking_date)
        spaces = self.space_repo.list_all()
        day_bookings = self.booking_repo.list_filtered({"date": valid_date})

        grouped: dict[int, list[dict[str, Any]]] = {}
        for item in day_bookings:
            if item["status"] == "cancelada":
                continue
            grouped.setdefault(int(item["space_id"]), []).append(item)

        operating_hours = (self.CLOSE_MINUTES - self.OPEN_MINUTES) / 60
        schedule_spaces: list[dict[str, Any]] = []
        for space in spaces:
            assert space.id is not None
            space_bookings = sorted(
                grouped.get(space.id, []),
                key=lambda b: (b["start_time"], b["id"]),
            )
            booked_hours = round(
                sum(float(b["duration_hours"]) for b in space_bookings), 2
            )
            occupancy_pct = round((booked_hours / operating_hours) * 100, 1)
            schedule_spaces.append(
                {
                    **space.to_dict(),
                    "booked_hours": booked_hours,
                    "occupancy_pct": occupancy_pct,
                    "bookings": space_bookings,
                }
            )

        return {
            "booking_date": valid_date,
            "open_time": self._minutes_to_hhmm(self.OPEN_MINUTES),
            "close_time": self._minutes_to_hhmm(self.CLOSE_MINUTES),
            "spaces": schedule_spaces,
        }

    def get_analytics(self, target_date: str | None = None) -> dict[str, Any]:
        """Calcula métricas de ingresos, estados, ocupación y desglose por sala y hora."""
        ref_date = (
            date.today().isoformat()
            if target_date is None or str(target_date).strip() == ""
            else self._validate_date(target_date)
        )

        spaces = self.space_repo.list_all()
        bookings = self.booking_repo.list_filtered()

        status_counts: dict[str, int] = {
            "confirmada": 0,
            "completada": 0,
            "cancelada": 0,
        }
        total_revenue = 0.0
        target_date_revenue = 0.0
        total_hours = 0.0
        today_hours = 0.0
        active_bookings = 0

        space_stats: dict[int, dict[str, Any]] = {}
        for space in spaces:
            assert space.id is not None
            space_stats[space.id] = {
                "space_id": space.id,
                "space_name": space.name,
                "category": space.category,
                "floor": space.floor,
                "is_active": space.is_active,
                "bookings_count": 0,
                "cancelled_count": 0,
                "total_hours": 0.0,
                "revenue": 0.0,
                "today_hours": 0.0,
                "today_occupancy_pct": 0.0,
            }

        hour_buckets: dict[int, dict[str, int]] = {
            hour: {"bookings_count": 0, "today_count": 0}
            for hour in range(8, 21)
        }
        hour_active_spaces: dict[int, set[int]] = {
            hour: set() for hour in range(8, 21)
        }

        for booking in bookings:
            status = str(booking["status"])
            if status in status_counts:
                status_counts[status] += 1

            space_id = int(booking["space_id"])
            if status == "cancelada":
                if space_id in space_stats:
                    space_stats[space_id]["cancelled_count"] += 1
                continue

            active_bookings += 1
            price = float(booking["total_price"])
            duration = float(booking["duration_hours"])
            is_target_day = booking["booking_date"] == ref_date
            space_entry = space_stats.get(space_id)
            is_active_space = bool(space_entry and space_entry["is_active"])

            total_revenue += price
            total_hours += duration
            if is_target_day:
                target_date_revenue += price
                if is_active_space:
                    today_hours += duration

            if space_entry is not None:
                space_entry["bookings_count"] += 1
                space_entry["total_hours"] += duration
                space_entry["revenue"] += price
                if is_target_day:
                    space_entry["today_hours"] += duration

            start_min = self._hhmm_to_minutes(str(booking["start_time"]))
            end_min = self._hhmm_to_minutes(str(booking["end_time"]))
            for hour in range(8, 21):
                hour_start = hour * 60
                hour_end = (hour + 1) * 60
                if start_min < hour_end and end_min > hour_start:
                    hour_buckets[hour]["bookings_count"] += 1
                    if is_target_day and is_active_space:
                        hour_buckets[hour]["today_count"] += 1
                        hour_active_spaces[hour].add(space_id)

        operating_hours = (self.CLOSE_MINUTES - self.OPEN_MINUTES) / 60
        active_spaces_count = sum(1 for s in spaces if s.is_active)
        occupancy_today_pct = (
            min(
                100.0,
                round(
                    (today_hours / (active_spaces_count * operating_hours))
                    * 100,
                    1,
                ),
            )
            if active_spaces_count > 0
            else 0.0
        )

        by_space: list[dict[str, Any]] = []
        for entry in space_stats.values():
            entry["total_hours"] = round(entry["total_hours"], 2)
            entry["revenue"] = round(entry["revenue"], 2)
            entry["today_hours"] = round(entry["today_hours"], 2)
            entry["today_occupancy_pct"] = round(
                (entry["today_hours"] / operating_hours) * 100, 1
            )
            by_space.append(entry)

        by_hour: list[dict[str, Any]] = []
        for hour in range(8, 21):
            counts = hour_buckets[hour]
            hour_occupancy = (
                min(
                    100.0,
                    round(
                        (len(hour_active_spaces[hour]) / active_spaces_count)
                        * 100,
                        1,
                    ),
                )
                if active_spaces_count > 0
                else 0.0
            )
            by_hour.append(
                {
                    "hour": f"{hour:02d}:00",
                    "bookings_count": counts["bookings_count"],
                    "today_count": counts["today_count"],
                    "occupancy_pct": hour_occupancy,
                }
            )

        return {
            "target_date": ref_date,
            "total_bookings": len(bookings),
            "active_bookings": active_bookings,
            "total_revenue": round(total_revenue, 2),
            "target_date_revenue": round(target_date_revenue, 2),
            "total_hours": round(total_hours, 2),
            "occupancy_today_pct": occupancy_today_pct,
            "active_spaces_count": active_spaces_count,
            "total_spaces_count": len(spaces),
            "status_counts": status_counts,
            "by_space": by_space,
            "by_hour": by_hour,
        }

    def export_csv(self, filters: Mapping[str, Any] | None = None) -> str:
        """Genera un informe CSV UTF-8 con BOM de las reservas filtradas."""
        bookings = self.booking_repo.list_filtered(filters)
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(
            [
                "Código",
                "Fecha",
                "Inicio",
                "Fin",
                "Duración (h)",
                "Sala",
                "Planta",
                "Título",
                "Cliente",
                "Email",
                "Asistentes",
                "Importe (€)",
                "Estado",
                "Notas",
                "Creada",
            ]
        )
        for item in bookings:
            writer.writerow(
                [
                    item["reference_code"],
                    item["booking_date"],
                    item["start_time"],
                    item["end_time"],
                    f"{float(item['duration_hours']):.2f}",
                    item["space_name"],
                    item["space_floor"],
                    item["title"],
                    item["customer_name"],
                    item["customer_email"],
                    item["attendees"],
                    f"{float(item['total_price']):.2f}",
                    item["status"],
                    item["notes"],
                    item["created_at"] or "",
                ]
            )
        return "\ufeff" + buffer.getvalue()
