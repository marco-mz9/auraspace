from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from playwright.sync_api import expect
import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Page

pytestmark = pytest.mark.e2e


def _select_booking_space_for_date(
    page: Page, space_name: str, target_date: str
) -> str:
    """Fija la fecha y selecciona la sala esperada sincronizando /api/availability."""
    space_option = page.locator("#booking-space option", has_text=space_name).first
    space_id = space_option.get_attribute("value")
    assert space_id is not None

    with page.expect_response(
        lambda r: "/api/availability" in r.url
        and f"date={target_date}" in r.url
        and r.status == 200
    ):
        page.locator("#booking-date").fill(target_date)

    if page.locator("#booking-space").input_value() != space_id:
        with page.expect_response(
            lambda r: "/api/availability" in r.url
            and f"space_id={space_id}" in r.url
            and f"date={target_date}" in r.url
            and r.status == 200
        ):
            page.locator("#booking-space").select_option(space_id)

    return space_id


def test_booking_modal_validation_slots_price_creation_and_overlap_409(
    page: Page,
    live_server: str,
    future_date_factory: Callable[[int], str],
) -> None:
    """Valida errores en vacío, selección visual de bloques, cálculo de importe, alta y conflicto 409."""
    page.goto(live_server, wait_until="networkidle")
    target_date = future_date_factory(20)

    with page.expect_response(
        lambda r: "/api/availability" in r.url and r.status == 200
    ):
        page.locator("#btn-new-booking").click()
    expect(page.locator("#booking-modal")).to_be_visible()

    # Envío con campos obligatorios vacíos -> muestra #booking-form-error
    with page.expect_response(
        lambda r: r.url.endswith("/api/bookings")
        and r.request.method == "POST"
        and r.status == 400
    ):
        page.locator("#booking-submit-btn").click()
    expect(page.locator("#booking-form-error")).to_be_visible()

    _select_booking_space_for_date(page, "Sala Aura", target_date)
    expect(page.locator("#availability-slots .slot-item")).to_have_count(26)

    # Primer clic: selecciona un bloque de 30 min (10:00-10:30 -> 17,50 €)
    page.locator('#availability-slots .slot-item[data-start="10:00"]').click()
    expect(page.locator("#booking-start")).to_have_value("10:00")
    expect(page.locator("#booking-end")).to_have_value("10:30")
    expect(page.locator("#booking-price-preview")).to_have_text("17,50 €")

    # Segundo clic posterior: extiende la franja (10:00-12:00 -> 4 bloques -> 70,00 €)
    page.locator('#availability-slots .slot-item[data-start="11:30"]').click()
    expect(page.locator("#booking-start")).to_have_value("10:00")
    expect(page.locator("#booking-end")).to_have_value("12:00")
    expect(page.locator("#availability-slots .slot-item.slot-selected")).to_have_count(
        4
    )
    expect(page.locator("#booking-price-preview")).to_have_text("70,00 €")

    page.locator("#booking-title").fill("Comité Producto E2E")
    page.locator("#booking-customer-name").fill("Laura Martín")
    page.locator("#booking-customer-email").fill("laura.martin@empresa.es")
    page.locator("#booking-attendees").fill("5")
    page.locator("#booking-notes").fill("Reserva creada desde Playwright")

    with page.expect_response(
        lambda r: r.url.endswith("/api/bookings")
        and r.request.method == "POST"
        and r.status == 201
    ):
        page.locator("#booking-submit-btn").click()

    expect(page.locator("#booking-modal")).to_be_hidden()
    toast = page.locator("#toast-container .toast").last
    expect(toast).to_be_visible()
    expect(toast).to_contain_text("AURA-")
    expect(toast).to_contain_text("70,00 €")

    # Segundo intento solapado -> bloques ocupados deshabilitados y error HTTP 409 visible
    with page.expect_response(
        lambda r: "/api/availability" in r.url and r.status == 200
    ):
        page.locator("#btn-new-booking").click()

    _select_booking_space_for_date(page, "Sala Aura", target_date)
    occupied_slot = page.locator(
        '#availability-slots .slot-item[data-start="10:00"]'
    )
    expect(occupied_slot).to_be_disabled()
    expect(occupied_slot).to_have_class(
        "slot-item slot-occupied"
    )

    page.locator("#booking-start").select_option("10:30")
    page.locator("#booking-end").select_option("12:30")
    page.locator("#booking-title").fill("Intento Solapado E2E")
    page.locator("#booking-customer-name").fill("Carlos Vega")
    page.locator("#booking-customer-email").fill("carlos.vega@empresa.es")
    page.locator("#booking-attendees").fill("3")

    with page.expect_response(
        lambda r: r.url.endswith("/api/bookings")
        and r.request.method == "POST"
        and r.status == 409
    ):
        page.locator("#booking-submit-btn").click()

    expect(page.locator("#booking-modal")).to_be_visible()
    expect(page.locator("#booking-form-error")).to_be_visible()
    expect(page.locator("#booking-form-error")).to_contain_text("ya está reservada")
    page.locator("#booking-modal-close").click()
    expect(page.locator("#booking-modal")).to_be_hidden()


def test_quick_booking_from_daily_schedule(
    page: Page,
    live_server: str,
    future_date_factory: Callable[[int], str],
) -> None:
    """Permite navegar por fechas en Agenda Diaria, crear desde un hueco libre y abrir edición."""
    page.goto(live_server, wait_until="networkidle")
    target_date = future_date_factory(21)

    with page.expect_response(
        lambda r: "/api/schedule" in r.url and r.status == 200
    ):
        page.locator("#tab-schedule").click()

    for btn_id in ("#schedule-yesterday", "#schedule-today", "#schedule-tomorrow"):
        with page.expect_response(
            lambda r: "/api/schedule" in r.url and r.status == 200
        ):
            page.locator(btn_id).click()

    with page.expect_response(
        lambda r: "/api/schedule" in r.url
        and f"date={target_date}" in r.url
        and r.status == 200
    ):
        page.locator("#schedule-date").fill(target_date)

    aura_row = page.locator("#schedule-board .schedule-row", has_text="Sala Aura")
    with page.expect_response(
        lambda r: "/api/availability" in r.url
        and f"date={target_date}" in r.url
        and r.status == 200
    ):
        aura_row.locator(
            '.timeline-slot-bg[data-action="schedule-new"][data-start="14:00"]'
        ).click()

    expect(page.locator("#booking-modal")).to_be_visible()
    expect(page.locator("#booking-date")).to_have_value(target_date)
    expect(page.locator("#booking-start")).to_have_value("14:00")
    expect(page.locator("#booking-end")).to_have_value("15:00")

    page.locator("#booking-title").fill("Sesión Agenda E2E")
    page.locator("#booking-customer-name").fill("Marta Soler")
    page.locator("#booking-customer-email").fill("marta.soler@empresa.es")
    page.locator("#booking-attendees").fill("4")

    with page.expect_response(
        lambda r: r.url.endswith("/api/bookings")
        and r.request.method == "POST"
        and r.status == 201
    ):
        page.locator("#booking-submit-btn").click()

    expect(page.locator("#booking-modal")).to_be_hidden()

    created_block = aura_row.locator(
        '.timeline-block[data-action="schedule-edit"]',
        has_text="Sesión Agenda E2E",
    )
    expect(created_block).to_be_visible()

    with page.expect_response(
        lambda r: "/api/availability" in r.url and r.status == 200
    ):
        created_block.click()
    expect(page.locator("#booking-modal")).to_be_visible()
    expect(page.locator("#booking-modal-title")).to_have_text("Editar Reserva")
    page.locator("#booking-modal-close").click()


def test_booking_lifecycle_edit_cancel_reactivate_complete_in_table(
    page: Page,
    live_server: str,
    future_date_factory: Callable[[int], str],
) -> None:
    """Cubre filtrar, editar, cancelar, reactivar y completar una reserva desde #bookings-tbody."""
    page.goto(live_server, wait_until="networkidle")
    target_date = future_date_factory(22)

    spaces_resp = page.request.get(f"{live_server}/api/spaces")
    assert spaces_resp.ok
    sala_aura = next(
        s for s in spaces_resp.json()["spaces"] if s["name"] == "Sala Aura"
    )

    create_resp = page.request.post(
        f"{live_server}/api/bookings",
        data={
            "space_id": sala_aura["id"],
            "title": "Ciclo E2E Base",
            "customer_name": "Hugo Navarro",
            "customer_email": "hugo.navarro@empresa.es",
            "attendees": 4,
            "booking_date": target_date,
            "start_time": "10:00",
            "end_time": "12:00",
            "notes": "Prueba ciclo completo",
        },
    )
    assert create_resp.status == 201

    with page.expect_response(
        lambda r: "/api/bookings" in r.url and r.status == 200
    ):
        page.locator("#tab-bookings").click()
    expect(page.locator("#view-bookings")).to_be_visible()

    with page.expect_response(
        lambda r: "/api/bookings" in r.url
        and f"date={target_date}" in r.url
        and r.status == 200
    ):
        page.locator("#bookings-filter-date").fill(target_date)

    with page.expect_response(
        lambda r: "/api/bookings" in r.url
        and "q=Ciclo" in r.url
        and r.status == 200
    ):
        page.locator("#bookings-filter-q").fill("Ciclo E2E")

    rows = page.locator("#bookings-tbody tr")
    expect(rows).to_have_count(1)
    row = rows.first

    # 1) Editar reserva -> recalcula duración/importe (10:00-13:00 -> 105,00 €)
    with page.expect_response(
        lambda r: "/api/availability" in r.url and r.status == 200
    ):
        row.locator('button[data-action="edit-booking"]').click()
    expect(page.locator("#booking-modal-title")).to_have_text("Editar Reserva")
    page.locator("#booking-title").fill("Ciclo E2E Editado")
    page.locator("#booking-end").select_option("13:00")

    with page.expect_response(
        lambda r: "/api/bookings" in r.url
        and r.request.method == "GET"
        and r.status == 200
    ):
        page.locator("#booking-submit-btn").click()

    expect(page.locator("#booking-modal")).to_be_hidden()
    expect(row).to_contain_text("Ciclo E2E Editado")
    expect(row).to_contain_text("105,00 €")

    # 2) Cancelar reserva -> deshabilita botón Editar y muestra Reactivar
    with page.expect_response(
        lambda r: "/api/bookings" in r.url
        and r.request.method == "GET"
        and r.status == 200
    ):
        row.locator('button[data-action="cancel-booking"]').click()

    expect(row).to_contain_text("Cancelada")
    expect(row.locator('button[data-action="edit-booking"]')).to_be_disabled()
    expect(row.locator('button[data-action="reactivate-booking"]')).to_be_visible()

    # Filtrar por estado cancelada y volver a todos
    with page.expect_response(
        lambda r: "/api/bookings" in r.url
        and "status=cancelada" in r.url
        and r.status == 200
    ):
        page.locator("#bookings-filter-status").select_option("cancelada")
    expect(rows).to_have_count(1)

    with page.expect_response(
        lambda r: "/api/bookings" in r.url
        and "status=" not in r.url
        and r.status == 200
    ):
        page.locator("#bookings-filter-status").select_option("")
    expect(rows).to_have_count(1)

    # 3) Reactivar reserva -> vuelve a Confirmada
    with page.expect_response(
        lambda r: "/api/bookings" in r.url
        and r.request.method == "GET"
        and r.status == 200
    ):
        row.locator('button[data-action="reactivate-booking"]').click()

    expect(row).to_contain_text("Confirmada")
    expect(row.locator('button[data-action="complete-booking"]')).to_be_visible()

    # 4) Completar reserva -> pasa a Completada
    with page.expect_response(
        lambda r: "/api/bookings" in r.url
        and r.request.method == "GET"
        and r.status == 200
    ):
        row.locator('button[data-action="complete-booking"]').click()

    expect(row).to_contain_text("Completada")
    expect(row.locator('button[data-action="complete-booking"]')).to_have_count(0)

    # 5) Limpiar filtros muestra todo el listado
    with page.expect_response(
        lambda r: r.url.endswith("/api/bookings") and r.status == 200
    ):
        page.locator("#bookings-filter-reset").click()
    assert page.locator("#bookings-tbody tr").count() >= 15
