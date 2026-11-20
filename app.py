from __future__ import annotations

from datetime import date
from pathlib import Path
import re
import sys
from typing import Any

from flask import Flask, Response, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "auraspace.db"

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from database import DatabaseManager
from repositories import BookingRepository, SpaceRepository
from services import (
    ConflictError,
    DomainError,
    NotFoundError,
    ReservationService,
    ValidationError,
)


def _get_json_body() -> dict[str, Any]:
    """Extrae el cuerpo JSON de la petición y valida que sea un objeto."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationError(
            "El cuerpo de la petición debe ser un objeto JSON válido."
        )
    return payload


def _parse_optional_int_param(name: str) -> int | None:
    """Convierte un parámetro de consulta opcional en entero positivo."""
    raw = request.args.get(name)
    if raw is None or raw.strip() == "":
        return None
    cleaned = raw.strip()
    if not re.fullmatch(r"[+-]?\d+", cleaned):
        raise ValidationError(
            f"El parámetro '{name}' debe ser un número entero válido."
        )
    parsed = int(cleaned)
    if parsed <= 0:
        raise ValidationError(
            f"El parámetro '{name}' debe ser mayor que 0."
        )
    return parsed


def _parse_required_int_param(name: str) -> int:
    """Exige y valida un parámetro de consulta como entero positivo."""
    parsed = _parse_optional_int_param(name)
    if parsed is None:
        raise ValidationError(f"El parámetro '{name}' es obligatorio.")
    return parsed


def _extract_booking_filters() -> dict[str, Any]:
    """Extrae los filtros admitidos para consultar o exportar reservas."""
    return {
        "q": request.args.get("q", ""),
        "space_id": _parse_optional_int_param("space_id"),
        "status": request.args.get("status", ""),
        "date": (
            request.args.get("date")
            or request.args.get("booking_date")
            or ""
        ).strip(),
    }


def create_app(
    db_path: str | Path | None = None,
    seed: bool = True,
) -> Flask:
    """Crea y configura la aplicación Flask de AuraSpace."""
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )
    app.json.ensure_ascii = False

    db = DatabaseManager(db_path or DEFAULT_DB_PATH)
    db.init_schema()
    if seed:
        db.seed_initial_data()

    space_repo = SpaceRepository(db)
    booking_repo = BookingRepository(db)
    service = ReservationService(db, space_repo, booking_repo)

    app.config["DB_PATH"] = db.db_path
    app.extensions["db"] = db
    app.extensions["service"] = service

    @app.errorhandler(ValidationError)
    def handle_validation_error(
        exc: ValidationError,
    ) -> tuple[Response, int]:
        """Devuelve JSON 400 ante errores de validación."""
        return jsonify({"error": str(exc)}), 400

    @app.errorhandler(NotFoundError)
    def handle_not_found_error(exc: NotFoundError) -> tuple[Response, int]:
        """Devuelve JSON 404 cuando no existe el recurso solicitado."""
        return jsonify({"error": str(exc)}), 404

    @app.errorhandler(ConflictError)
    def handle_conflict_error(exc: ConflictError) -> tuple[Response, int]:
        """Devuelve JSON 409 ante conflictos de horario o duplicidad."""
        return jsonify({"error": str(exc)}), 409

    @app.errorhandler(DomainError)
    def handle_domain_error(exc: DomainError) -> tuple[Response, int]:
        """Devuelve JSON uniforme para cualquier otro error de dominio."""
        return jsonify({"error": str(exc)}), exc.status_code

    @app.errorhandler(404)
    def handle_http_not_found(_exc: Exception) -> tuple[Response, int]:
        """Devuelve JSON 404 para rutas inexistentes."""
        return jsonify({"error": "Recurso no encontrado."}), 404

    @app.errorhandler(405)
    def handle_method_not_allowed(_exc: Exception) -> tuple[Response, int]:
        """Devuelve JSON 405 cuando el método HTTP no está permitido."""
        return jsonify({"error": "Método HTTP no permitido."}), 405

    @app.errorhandler(500)
    def handle_internal_server_error(_exc: Exception) -> tuple[Response, int]:
        """Devuelve JSON 500 uniforme sin exponer detalles internos ni HTML."""
        return jsonify({"error": "Error interno del servidor."}), 500

    @app.get("/")
    def index() -> str:
        """Sirve la página principal de la aplicación."""
        return render_template("index.html")

    @app.get("/favicon.ico")
    def favicon() -> Response:
        """Sirve el icono local SVG para evitar errores 404 en navegadores."""
        return app.send_static_file("favicon.svg")

    @app.get("/api/spaces")
    def list_spaces() -> tuple[Response, int]:
        """Lista las salas filtradas por búsqueda, categoría, aforo o estado."""
        filters = {
            "q": request.args.get("q", ""),
            "category": request.args.get("category", ""),
            "min_capacity": _parse_optional_int_param("min_capacity"),
            "active_only": request.args.get("active_only"),
        }
        spaces = service.list_spaces(filters)
        return jsonify({"spaces": spaces, "total": len(spaces)}), 200

    @app.post("/api/spaces")
    def create_space() -> tuple[Response, int]:
        """Crea una nueva sala de coworking."""
        created = service.create_space(_get_json_body())
        return jsonify(created), 201

    @app.patch("/api/spaces/<int:space_id>")
    def update_space_status(space_id: int) -> tuple[Response, int]:
        """Activa o desactiva una sala existente."""
        payload = _get_json_body()
        if "is_active" not in payload:
            raise ValidationError("El campo 'is_active' es obligatorio.")
        updated = service.update_space_status(space_id, payload["is_active"])
        return jsonify(updated), 200

    @app.get("/api/availability")
    def get_availability() -> tuple[Response, int]:
        """Devuelve los 26 bloques horarios de una sala para una fecha."""
        space_id = _parse_required_int_param("space_id")
        booking_date = (
            request.args.get("date")
            or request.args.get("booking_date")
            or date.today().isoformat()
        ).strip()
        exclude_booking_id = _parse_optional_int_param("exclude_booking_id")
        availability = service.get_availability(
            space_id=space_id,
            booking_date=booking_date,
            exclude_booking_id=exclude_booking_id,
        )
        return jsonify(availability), 200

    @app.get("/api/schedule")
    def get_schedule() -> tuple[Response, int]:
        """Devuelve el cuadrante diario de salas y reservas activas."""
        booking_date = (
            request.args.get("date")
            or request.args.get("booking_date")
            or date.today().isoformat()
        ).strip()
        schedule = service.get_daily_schedule(booking_date)
        return jsonify(schedule), 200

    @app.get("/api/bookings")
    def list_bookings() -> tuple[Response, int]:
        """Lista las reservas aplicando filtros de búsqueda, sala, estado y fecha."""
        bookings = service.list_bookings(_extract_booking_filters())
        return jsonify({"bookings": bookings, "total": len(bookings)}), 200

    @app.post("/api/bookings")
    def create_booking() -> tuple[Response, int]:
        """Registra una nueva reserva validando reglas de negocio y disponibilidad."""
        created = service.create_booking(_get_json_body())
        return jsonify(created), 201

    @app.put("/api/bookings/<int:booking_id>")
    def update_booking(booking_id: int) -> tuple[Response, int]:
        """Modifica una reserva existente recalculando precio y disponibilidad."""
        updated = service.update_booking(booking_id, _get_json_body())
        return jsonify(updated), 200

    @app.patch("/api/bookings/<int:booking_id>/status")
    def update_booking_status(booking_id: int) -> tuple[Response, int]:
        """Actualiza el estado de una reserva existente."""
        payload = _get_json_body()
        if "status" not in payload:
            raise ValidationError("El campo 'status' es obligatorio.")
        updated = service.change_status(
            booking_id=booking_id,
            status=payload["status"],
            notes=payload.get("notes"),
        )
        return jsonify(updated), 200

    @app.get("/api/bookings/export")
    def export_bookings() -> Response:
        """Exporta las reservas filtradas en formato CSV UTF-8 con BOM."""
        csv_text = service.export_csv(_extract_booking_filters())
        return Response(
            csv_text.encode("utf-8"),
            status=200,
            headers={
                "Content-Type": "text/csv; charset=utf-8",
                "Content-Disposition": (
                    'attachment; filename="auraspace_reservas.csv"'
                ),
            },
        )

    @app.get("/api/analytics")
    def get_analytics() -> tuple[Response, int]:
        """Devuelve indicadores y desglose analítico de ocupación e ingresos."""
        target_date = request.args.get("date")
        analytics = service.get_analytics(target_date=target_date)
        return jsonify(analytics), 200

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="127.0.0.1", port=5000, debug=True)
