from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from app import create_app
from database import DatabaseManager

if TYPE_CHECKING:
    from flask import Flask
    from flask.testing import FlaskClient


@pytest.fixture()
def db_file(tmp_path: Path) -> Path:
    """Devuelve una ruta de base de datos SQLite aislada por cada prueba."""
    return tmp_path / "test_auraspace.db"


@pytest.fixture()
def db_manager(db_file: Path) -> DatabaseManager:
    """Devuelve un DatabaseManager con el esquema inicializado y sin semilla."""
    manager = DatabaseManager(db_file)
    manager.init_schema()
    return manager


@pytest.fixture()
def empty_app(db_file: Path) -> Flask:
    """Crea una aplicación Flask aislada con base de datos vacía (sin semilla)."""
    flask_app = create_app(db_path=db_file, seed=False)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture()
def empty_client(empty_app: Flask) -> FlaskClient:
    """Devuelve el cliente HTTP de Flask sobre la aplicación sin semilla."""
    return empty_app.test_client()


@pytest.fixture()
def app(db_file: Path) -> Flask:
    """Crea una aplicación Flask aislada con la semilla inicial cargada."""
    flask_app = create_app(db_path=db_file, seed=True)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    """Devuelve el cliente HTTP de Flask sobre la aplicación con semilla."""
    return app.test_client()


@pytest.fixture()
def future_date_factory() -> Callable[[int], str]:
    """Devuelve una fábrica de fechas ISO futuras relativas a date.today()."""

    def _make_date(days_ahead: int = 15) -> str:
        return (date.today() + timedelta(days=days_ahead)).isoformat()

    return _make_date


@pytest.fixture()
def booking_payload_factory(
    future_date_factory: Callable[[int], str],
) -> Callable[..., dict[str, Any]]:
    """Devuelve una fábrica de payloads válidos de reserva personalizables."""

    def _make_payload(
        space_id: int = 1,
        booking_date: str | None = None,
        **overrides: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "space_id": space_id,
            "title": "Reunión de planificación",
            "customer_name": "Laura Martín",
            "customer_email": "laura.martin@empresa.es",
            "attendees": 4,
            "booking_date": booking_date or future_date_factory(15),
            "start_time": "10:00",
            "end_time": "12:00",
            "notes": "Requiere pantalla HDMI",
        }
        payload.update(overrides)
        return payload

    return _make_payload
