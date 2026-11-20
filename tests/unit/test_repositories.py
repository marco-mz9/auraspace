from __future__ import annotations

from typing import Any

import pytest

from database import DatabaseManager
from models import Booking
from repositories import BookingRepository, SpaceRepository

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Pruebas unitarias de SpaceRepository
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        (2.5, True),
        (0.0, False),
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("si", True),
        ("sí", True),
        ("yes", True),
        (" SI ", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("", False),
        (None, False),
        ([], False),
        (["x"], True),
    ],
)
def test_space_repository_parse_bool(raw_value: Any, expected: bool) -> None:
    """_parse_bool convierte booleanos, números, textos y otros tipos correctamente."""
    assert SpaceRepository._parse_bool(raw_value) is expected


def test_space_repository_create_and_get_by_id(db_manager: DatabaseManager) -> None:
    """create persiste salas activas y get_by_id funciona con conexión propia o externa."""
    repo = SpaceRepository(db_manager)

    s1 = repo.create(
        name="Sala Alfa",
        category="Sala de reuniones",
        floor="Planta 1",
        capacity=8,
        hourly_rate=35.0,
    )
    s2 = repo.create(
        name="Sala Beta",
        category="Zona creativa",
        floor="Planta 2",
        capacity=14,
        hourly_rate=55.5,
        equipment="Proyector 4K, Pizarra",
    )

    assert s1.id is not None
    assert s1.is_active is True
    assert s1.equipment == ""
    assert s1.created_at is not None

    assert s2.id is not None
    assert s2.equipment == "Proyector 4K, Pizarra"

    fetched_own = repo.get_by_id(s1.id)
    assert fetched_own is not None
    assert fetched_own.name == "Sala Alfa"

    assert repo.get_by_id(9999) is None

    conn = db_manager.get_connection()
    try:
        fetched_ext = repo.get_by_id(s2.id, conn=conn)
        assert fetched_ext is not None
        assert fetched_ext.name == "Sala Beta"
        assert repo.get_by_id(8888, conn=conn) is None
    finally:
        conn.close()


def test_space_repository_list_all_filters_and_ordering(
    db_manager: DatabaseManager,
) -> None:
    """list_all ordena activas primero luego alfabético y aplica todos los filtros."""
    repo = SpaceRepository(db_manager)

    s_zzz = repo.create(
        name="ZZZ Activa",
        category="Sala de reuniones",
        floor="Planta 1",
        capacity=10,
        hourly_rate=40.0,
        equipment="Pantalla 4K, Videoconferencia",
    )
    repo.create(
        name="BBB Activa",
        category="Auditorio",
        floor="Planta Baja",
        capacity=30,
        hourly_rate=110.0,
        equipment="Proyector láser, Streaming",
    )
    s_aaa_inactive = repo.create(
        name="AAA Inactiva",
        category="Sala de reuniones",
        floor="Planta 2",
        capacity=12,
        hourly_rate=45.0,
        equipment="Proyector portátil",
    )
    assert s_zzz.id is not None
    assert s_aaa_inactive.id is not None
    repo.update_status(s_aaa_inactive.id, False)

    # Sin filtros: activas primero (BBB, ZZZ) y luego inactivas (AAA)
    all_spaces = repo.list_all()
    assert [s.name for s in all_spaces] == ["BBB Activa", "ZZZ Activa", "AAA Inactiva"]

    # Búsqueda q en nombre, categoría y equipamiento (insensible a mayúsculas)
    by_equipment = repo.list_all({"q": "PROYECTOR"})
    assert {s.name for s in by_equipment} == {"BBB Activa", "AAA Inactiva"}

    by_category = repo.list_all({"category": "sala de reuniones"})
    assert [s.name for s in by_category] == ["ZZZ Activa", "AAA Inactiva"]

    by_capacity_int = repo.list_all({"min_capacity": 12})
    assert {s.name for s in by_capacity_int} == {"BBB Activa", "AAA Inactiva"}

    by_capacity_str = repo.list_all({"min_capacity": "12"})
    assert {s.name for s in by_capacity_str} == {"BBB Activa", "AAA Inactiva"}

    # min_capacity vacío no filtra
    assert len(repo.list_all({"min_capacity": ""})) == 3

    # active_only con distintos formatos booleanos
    assert [s.name for s in repo.list_all({"active_only": "sí"})] == [
        "BBB Activa",
        "ZZZ Activa",
    ]
    assert len(repo.list_all({"active_only": "false"})) == 3
    assert len(repo.list_all({"active_only": None})) == 3

    # Filtros combinados
    combined = repo.list_all(
        {
            "q": "proyector",
            "category": "Sala de reuniones",
            "min_capacity": 10,
            "active_only": True,
        }
    )
    assert combined == []

    combined_match = repo.list_all(
        {
            "q": "proyector",
            "category": "Auditorio",
            "min_capacity": 20,
            "active_only": "true",
        }
    )
    assert [s.name for s in combined_match] == ["BBB Activa"]


def test_space_repository_update_status_existing_and_missing(
    db_manager: DatabaseManager,
) -> None:
    """update_status cambia el estado operativo o retorna None si la sala no existe."""
    repo = SpaceRepository(db_manager)
    created = repo.create(
        name="Sala Estado",
        category="Cabina individual",
        floor="Planta 1",
        capacity=2,
        hourly_rate=15.0,
    )
    assert created.id is not None

    deactivated = repo.update_status(created.id, False)
    assert deactivated is not None
    assert deactivated.is_active is False

    reactivated = repo.update_status(created.id, True)
    assert reactivated is not None
    assert reactivated.is_active is True

    assert repo.update_status(99999, False) is None


# ---------------------------------------------------------------------------
# Pruebas unitarias de BookingRepository
# ---------------------------------------------------------------------------


def _seed_two_spaces(db_manager: DatabaseManager) -> tuple[int, int]:
    """Crea dos salas de prueba y devuelve sus IDs."""
    space_repo = SpaceRepository(db_manager)
    s1 = space_repo.create(
        name="Sala Norte",
        category="Sala de reuniones",
        floor="Planta 1",
        capacity=8,
        hourly_rate=35.0,
    )
    s2 = space_repo.create(
        name="Sala Sur",
        category="Oficina privada",
        floor="Planta 2",
        capacity=6,
        hourly_rate=40.0,
    )
    assert s1.id is not None and s2.id is not None
    return s1.id, s2.id


def test_booking_repository_insert_dict_and_model_and_get_by_id(
    db_manager: DatabaseManager,
) -> None:
    """insert soporta dict (notes=None) y modelo Booking; get_by_id soporta conn=None."""
    space_id, _ = _seed_two_spaces(db_manager)
    booking_repo = BookingRepository(db_manager)

    conn = db_manager.get_connection()
    try:
        with conn:
            created_from_dict = booking_repo.insert(
                conn,
                {
                    "reference_code": "AURA-20261201-D001",
                    "space_id": space_id,
                    "title": "Reserva Dict",
                    "customer_name": "Lucía Gómez",
                    "customer_email": "lucia@empresa.es",
                    "attendees": 4,
                    "booking_date": "2026-12-01",
                    "start_time": "09:00",
                    "end_time": "11:00",
                    "total_price": 70.0,
                    "notes": None,
                },
            )
            booking_model = Booking(
                reference_code="AURA-20261201-M002",
                space_id=space_id,
                title="Reserva Modelo",
                customer_name="Mario Sanz",
                customer_email="mario@empresa.es",
                attendees=3,
                booking_date="2026-12-01",
                start_time="12:00",
                end_time="13:30",
                total_price=52.5,
                status="completada",
                notes="Con pizarra",
            )
            created_from_model = booking_repo.insert(conn, booking_model)
    finally:
        conn.close()

    assert created_from_dict.id is not None
    assert created_from_dict.status == "confirmada"
    assert created_from_dict.notes == ""

    assert created_from_model.id is not None
    assert created_from_model.status == "completada"
    assert created_from_model.notes == "Con pizarra"

    # get_by_id sin conexión externa (own_conn=True)
    fetched = booking_repo.get_by_id(created_from_model.id)
    assert fetched is not None
    assert fetched.reference_code == "AURA-20261201-M002"
    assert booking_repo.get_by_id(99999) is None


def test_booking_repository_list_filtered_combinations_and_enrichment(
    db_manager: DatabaseManager,
) -> None:
    """list_filtered enriquece datos de sala y combina filtros q, space_id, status y fecha."""
    space_1, space_2 = _seed_two_spaces(db_manager)
    booking_repo = BookingRepository(db_manager)

    conn = db_manager.get_connection()
    try:
        with conn:
            booking_repo.insert(
                conn,
                {
                    "reference_code": "AURA-20261205-AA11",
                    "space_id": space_1,
                    "title": "Comité Alpha",
                    "customer_name": "Ana Torres",
                    "customer_email": "ana.torres@acme.es",
                    "attendees": 5,
                    "booking_date": "2026-12-05",
                    "start_time": "11:00",
                    "end_time": "12:30",
                    "total_price": 52.5,
                    "status": "confirmada",
                    "notes": "",
                },
            )
            booking_repo.insert(
                conn,
                {
                    "reference_code": "AURA-20261205-BB22",
                    "space_id": space_1,
                    "title": "Daily Beta",
                    "customer_name": "Pedro Gil",
                    "customer_email": "pedro.gil@beta.es",
                    "attendees": 3,
                    "booking_date": "2026-12-05",
                    "start_time": "09:00",
                    "end_time": "10:00",
                    "total_price": 35.0,
                    "status": "cancelada",
                    "notes": "",
                },
            )
            booking_repo.insert(
                conn,
                {
                    "reference_code": "AURA-20261206-CC33",
                    "space_id": space_2,
                    "title": "Sprint Review",
                    "customer_name": "Clara Vidal",
                    "customer_email": "clara@gamma.io",
                    "attendees": 4,
                    "booking_date": "2026-12-06",
                    "start_time": "10:00",
                    "end_time": "12:00",
                    "total_price": 80.0,
                    "status": "completada",
                    "notes": "",
                },
            )
    finally:
        conn.close()

    # Sin filtros: orden DESC por fecha, ASC por hora inicio
    all_items = booking_repo.list_filtered()
    assert [item["reference_code"] for item in all_items] == [
        "AURA-20261206-CC33",
        "AURA-20261205-BB22",
        "AURA-20261205-AA11",
    ]
    first = all_items[0]
    assert first["space_name"] == "Sala Sur"
    assert first["space_floor"] == "Planta 2"
    assert first["space_category"] == "Oficina privada"
    assert first["space_capacity"] == 6
    assert first["duration_hours"] == 2.0

    # Búsqueda q por código, título, cliente, email y nombre de sala
    assert len(booking_repo.list_filtered({"q": "CC33"})) == 1
    assert len(booking_repo.list_filtered({"q": "alpha"})) == 1
    assert len(booking_repo.list_filtered({"q": "pedro"})) == 1
    assert len(booking_repo.list_filtered({"q": "gamma.io"})) == 1
    assert len(booking_repo.list_filtered({"q": "sala norte"})) == 2

    # Filtros individuales y alias booking_date
    assert len(booking_repo.list_filtered({"space_id": space_2})) == 1
    assert len(booking_repo.list_filtered({"status": "COMPLETADA"})) == 1
    assert len(booking_repo.list_filtered({"date": "2026-12-05"})) == 2
    assert len(booking_repo.list_filtered({"booking_date": "2026-12-06"})) == 1

    # Filtros combinados
    combined = booking_repo.list_filtered(
        {
            "q": "torres",
            "space_id": space_1,
            "status": "confirmada",
            "date": "2026-12-05",
        }
    )
    assert len(combined) == 1
    assert combined[0]["reference_code"] == "AURA-20261205-AA11"


@pytest.mark.parametrize(
    ("cand_start", "cand_end", "should_overlap"),
    [
        ("10:00", "12:00", True),  # Exacto
        ("09:00", "11:00", True),  # Parcial al inicio
        ("11:00", "13:00", True),  # Parcial al final
        ("10:30", "11:30", True),  # Contenido
        ("09:30", "12:30", True),  # Envolvente
        ("08:00", "10:00", False),  # Contiguo anterior
        ("12:00", "14:00", False),  # Contiguo posterior
    ],
)
def test_booking_repository_find_overlap_geometries_and_contiguous(
    db_manager: DatabaseManager,
    cand_start: str,
    cand_end: str,
    should_overlap: bool,
) -> None:
    """find_overlap detecta los 5 patrones de solapamiento y permite contiguas exactas."""
    space_id, _ = _seed_two_spaces(db_manager)
    booking_repo = BookingRepository(db_manager)

    conn = db_manager.get_connection()
    try:
        with conn:
            base = booking_repo.insert(
                conn,
                {
                    "reference_code": "AURA-20261210-BASE",
                    "space_id": space_id,
                    "title": "Base",
                    "customer_name": "Base User",
                    "customer_email": "base@empresa.es",
                    "attendees": 2,
                    "booking_date": "2026-12-10",
                    "start_time": "10:00",
                    "end_time": "12:00",
                    "total_price": 70.0,
                    "status": "confirmada",
                    "notes": "",
                },
            )
        found = booking_repo.find_overlap(
            conn=conn,
            space_id=space_id,
            booking_date="2026-12-10",
            start_time=cand_start,
            end_time=cand_end,
        )
        if should_overlap:
            assert found is not None
            assert found.id == base.id
        else:
            assert found is None
    finally:
        conn.close()


def test_booking_repository_find_overlap_statuses_scope_and_exclude_id(
    db_manager: DatabaseManager,
) -> None:
    """find_overlap ignora canceladas, bloquea completadas y respeta exclude_booking_id."""
    space_1, space_2 = _seed_two_spaces(db_manager)
    booking_repo = BookingRepository(db_manager)

    conn = db_manager.get_connection()
    try:
        with conn:
            completed = booking_repo.insert(
                conn,
                {
                    "reference_code": "AURA-20261211-COMP",
                    "space_id": space_1,
                    "title": "Completada",
                    "customer_name": "Cliente 1",
                    "customer_email": "c1@empresa.es",
                    "attendees": 2,
                    "booking_date": "2026-12-11",
                    "start_time": "09:00",
                    "end_time": "11:00",
                    "total_price": 70.0,
                    "status": "completada",
                    "notes": "",
                },
            )
            booking_repo.insert(
                conn,
                {
                    "reference_code": "AURA-20261211-CANC",
                    "space_id": space_1,
                    "title": "Cancelada",
                    "customer_name": "Cliente 2",
                    "customer_email": "c2@empresa.es",
                    "attendees": 2,
                    "booking_date": "2026-12-11",
                    "start_time": "14:00",
                    "end_time": "16:00",
                    "total_price": 70.0,
                    "status": "cancelada",
                    "notes": "",
                },
            )

        assert completed.id is not None

        # Reserva completada sí bloquea
        overlap_completed = booking_repo.find_overlap(
            conn, space_1, "2026-12-11", "09:30", "10:30"
        )
        assert overlap_completed is not None
        assert overlap_completed.id == completed.id

        # Excluir su propio ID libera la comprobación
        assert (
            booking_repo.find_overlap(
                conn,
                space_1,
                "2026-12-11",
                "09:30",
                "10:30",
                exclude_booking_id=completed.id,
            )
            is None
        )

        # Excluir otro ID sigue detectando el conflicto
        assert (
            booking_repo.find_overlap(
                conn,
                space_1,
                "2026-12-11",
                "09:30",
                "10:30",
                exclude_booking_id=99999,
            )
            is not None
        )

        # Reserva cancelada no bloquea
        assert (
            booking_repo.find_overlap(conn, space_1, "2026-12-11", "14:00", "16:00")
            is None
        )

        # Otra sala u otra fecha no bloquean
        assert (
            booking_repo.find_overlap(conn, space_2, "2026-12-11", "09:00", "11:00")
            is None
        )
        assert (
            booking_repo.find_overlap(conn, space_1, "2026-12-12", "09:00", "11:00")
            is None
        )
    finally:
        conn.close()


def test_booking_repository_update_and_update_status(
    db_manager: DatabaseManager,
) -> None:
    """Valida update parcial/total/inválido y update_status con o sin notas."""
    space_1, space_2 = _seed_two_spaces(db_manager)
    booking_repo = BookingRepository(db_manager)

    conn = db_manager.get_connection()
    try:
        with conn:
            created = booking_repo.insert(
                conn,
                {
                    "reference_code": "AURA-20261212-UPD1",
                    "space_id": space_1,
                    "title": "Título inicial",
                    "customer_name": "Sofía Ruiz",
                    "customer_email": "sofia@empresa.es",
                    "attendees": 4,
                    "booking_date": "2026-12-12",
                    "start_time": "10:00",
                    "end_time": "12:00",
                    "total_price": 70.0,
                    "status": "confirmada",
                    "notes": "Nota inicial",
                },
            )
            assert created.id is not None

            # Update parcial ignorando campos no actualizables y notes=None -> ""
            partial = booking_repo.update(
                conn,
                created.id,
                {
                    "space_id": space_2,
                    "title": "Título editado",
                    "attendees": 6,
                    "total_price": 80.0,
                    "notes": None,
                    "reference_code": "IGNORADO",
                },
            )
            assert partial is not None
            assert partial.space_id == space_2
            assert partial.title == "Título editado"
            assert partial.attendees == 6
            assert partial.total_price == 80.0
            assert partial.notes == ""
            assert partial.reference_code == "AURA-20261212-UPD1"

            # Update con modelo Booking
            partial.title = "Título desde modelo"
            partial.notes = "Nota preservada"
            from_model = booking_repo.update(conn, created.id, partial)
            assert from_model is not None
            assert from_model.title == "Título desde modelo"
            assert from_model.notes == "Nota preservada"

            # Update sin campos válidos lanza ValueError
            with pytest.raises(ValueError, match="campos válidos"):
                booking_repo.update(conn, created.id, {})
            with pytest.raises(ValueError, match="campos válidos"):
                booking_repo.update(conn, created.id, {"reference_code": "OTRO"})

            # Update sobre ID inexistente retorna None
            assert (
                booking_repo.update(conn, 99999, {"title": "No existe"}) is None
            )

            # update_status sin notes conserva notas existentes
            status_only = booking_repo.update_status(
                conn, created.id, "completada", notes=None
            )
            assert status_only is not None
            assert status_only.status == "completada"
            assert status_only.notes == "Nota preservada"

            # update_status con notes explícitas reemplaza notas
            with_notes = booking_repo.update_status(
                conn, created.id, "cancelada", notes="Cancelada por cliente"
            )
            assert with_notes is not None
            assert with_notes.status == "cancelada"
            assert with_notes.notes == "Cancelada por cliente"

            # update_status sobre ID inexistente retorna None
            assert (
                booking_repo.update_status(conn, 99999, "cancelada", notes="x")
                is None
            )
    finally:
        conn.close()
