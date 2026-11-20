from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect
import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Page

pytestmark = pytest.mark.e2e


def test_initial_load_no_console_or_http_errors_and_six_cards(
    page: Page, live_server: str
) -> None:
    """La carga inicial renderiza las 6 salas sin errores de consola ni respuestas HTTP >= 400."""
    console_errors: list[str] = []
    http_errors: list[tuple[int, str]] = []

    page.on(
        "console",
        lambda msg: console_errors.append(msg.text)
        if msg.type == "error"
        else None,
    )
    page.on(
        "response",
        lambda res: http_errors.append((res.status, res.url))
        if res.status >= 400
        else None,
    )

    page.goto(live_server, wait_until="networkidle")

    expect(page.locator("#spaces-grid .space-card")).to_have_count(6)
    expect(page.locator("#spaces-count-label")).to_have_text(
        "6 espacios mostrados (6 activos)"
    )
    assert http_errors == [], f"Respuestas HTTP >= 400 detectadas: {http_errors}"
    assert console_errors == [], f"Errores de consola detectados: {console_errors}"


def test_navigation_across_all_four_tabs(page: Page, live_server: str) -> None:
    """La navegación entre Espacios, Agenda Diaria, Reservas y Analítica actualiza vistas y ARIA."""
    page.goto(live_server, wait_until="networkidle")

    expect(page.locator("#view-spaces")).to_be_visible()
    expect(page.locator("#tab-spaces")).to_have_attribute("aria-selected", "true")

    with page.expect_response(
        lambda r: "/api/schedule" in r.url and r.status == 200
    ):
        page.locator("#tab-schedule").click()
    expect(page.locator("#view-schedule")).to_be_visible()
    expect(page.locator("#view-spaces")).to_be_hidden()
    expect(page.locator("#tab-schedule")).to_have_attribute("aria-selected", "true")
    expect(page.locator("#schedule-board .schedule-row")).to_have_count(6)

    with page.expect_response(
        lambda r: "/api/bookings" in r.url and r.status == 200
    ):
        page.locator("#tab-bookings").click()
    expect(page.locator("#view-bookings")).to_be_visible()
    expect(page.locator("#view-schedule")).to_be_hidden()
    expect(page.locator("#tab-bookings")).to_have_attribute("aria-selected", "true")
    expect(page.locator("#bookings-tbody tr")).to_have_count(14)

    with page.expect_response(
        lambda r: "/api/analytics" in r.url and r.status == 200
    ):
        page.locator("#tab-analytics").click()
    expect(page.locator("#view-analytics")).to_be_visible()
    expect(page.locator("#view-bookings")).to_be_hidden()
    expect(page.locator("#tab-analytics")).to_have_attribute("aria-selected", "true")
    expect(page.locator("#analytics-by-space svg")).to_be_visible()
    expect(page.locator("#analytics-by-hour svg")).to_be_visible()

    with page.expect_response(
        lambda r: "/api/spaces" in r.url and r.status == 200
    ):
        page.locator("#tab-spaces").click()
    expect(page.locator("#view-spaces")).to_be_visible()
    expect(page.locator("#view-analytics")).to_be_hidden()
    expect(page.locator("#spaces-grid .space-card")).to_have_count(6)


def test_spaces_filters_and_empty_state(page: Page, live_server: str) -> None:
    """Los filtros de espacios combinados, el estado vacío y el botón Limpiar funcionan desde la UI."""
    page.goto(live_server, wait_until="networkidle")
    expect(page.locator("#spaces-grid .space-card")).to_have_count(6)

    with page.expect_response(
        lambda r: "/api/spaces" in r.url and "q=proyector" in r.url and r.status == 200
    ):
        page.locator("#spaces-filter-q").fill("proyector")
    expect(page.locator("#spaces-grid .space-card")).to_have_count(2)

    with page.expect_response(
        lambda r: "/api/spaces" in r.url and "category=" in r.url and r.status == 200
    ):
        page.locator("#spaces-filter-category").select_option("Sala de reuniones")
    expect(page.locator("#spaces-grid .space-card")).to_have_count(1)
    expect(page.locator("#spaces-grid .space-card").first).to_contain_text(
        "Estudio Zenith"
    )

    with page.expect_response(
        lambda r: "/api/spaces" in r.url
        and "min_capacity=20" in r.url
        and r.status == 200
    ):
        page.locator("#spaces-filter-capacity").fill("20")
    expect(page.locator("#spaces-grid .space-card")).to_have_count(0)
    expect(page.locator("#spaces-empty")).to_be_visible()

    with page.expect_response(
        lambda r: r.url.endswith("/api/spaces") and r.status == 200
    ):
        page.locator("#spaces-filter-reset").click()
    expect(page.locator("#spaces-grid .space-card")).to_have_count(6)
    expect(page.locator("#spaces-empty")).to_be_hidden()


def test_create_space_duplicate_error_and_maintenance_toggle(
    page: Page, live_server: str
) -> None:
    """Permite añadir una sala desde #space-modal, muestra error por duplicado y alterna mantenimiento."""
    page.goto(live_server, wait_until="networkidle")
    expect(page.locator("#spaces-grid .space-card")).to_have_count(6)

    page.locator("#btn-new-space").click()
    expect(page.locator("#space-modal")).to_be_visible()

    page.locator("#space-name").fill("Sala Ático E2E")
    page.locator("#space-category").fill("Sala de reuniones")
    page.locator("#space-floor").fill("Planta 4")
    page.locator("#space-capacity").fill("10")
    page.locator("#space-hourly-rate").fill("48")
    page.locator("#space-equipment").fill("Pizarra interactiva, Wi-Fi 6")

    with page.expect_response(
        lambda r: r.url.endswith("/api/spaces")
        and r.request.method == "POST"
        and r.status == 201
    ):
        page.locator("#space-submit-btn").click()

    expect(page.locator("#space-modal")).to_be_hidden()
    expect(page.locator("#toast-container .toast").last).to_contain_text(
        "Sala Ático E2E"
    )
    expect(page.locator("#spaces-grid .space-card")).to_have_count(7)

    # Intentar registrar el mismo nombre muestra error inline en #space-form-error
    page.locator("#btn-new-space").click()
    expect(page.locator("#space-modal")).to_be_visible()
    page.locator("#space-name").fill("Sala Ático E2E")
    page.locator("#space-category").fill("Sala de reuniones")
    page.locator("#space-floor").fill("Planta 4")
    page.locator("#space-capacity").fill("10")
    page.locator("#space-hourly-rate").fill("48")

    with page.expect_response(
        lambda r: r.url.endswith("/api/spaces")
        and r.request.method == "POST"
        and r.status == 409
    ):
        page.locator("#space-submit-btn").click()

    expect(page.locator("#space-modal")).to_be_visible()
    expect(page.locator("#space-form-error")).to_be_visible()
    expect(page.locator("#space-form-error")).to_contain_text("Ya existe")
    page.locator("#space-modal-close").click()
    expect(page.locator("#space-modal")).to_be_hidden()

    # Alternar Activa -> Mantenimiento sobre Sala Aura
    aura_card = page.locator("#spaces-grid .space-card", has_text="Sala Aura")
    toggle_btn = aura_card.locator('button[data-action="toggle-space"]')
    aura_id = toggle_btn.get_attribute("data-space-id")
    assert aura_id is not None

    book_btn = page.locator(
        f'button[data-action="book-space"][data-space-id="{aura_id}"]'
    )
    toggle_selector = (
        f'button[data-action="toggle-space"][data-space-id="{aura_id}"]'
    )

    with page.expect_response(
        lambda r: f"/api/spaces/{aura_id}" in r.url
        and r.request.method == "PATCH"
        and r.status == 200
    ):
        page.locator(toggle_selector).click()

    expect(book_btn).to_be_disabled()
    expect(page.locator(toggle_selector)).to_have_text("Activar sala")

    with page.expect_response(
        lambda r: "/api/spaces" in r.url
        and "active_only=true" in r.url
        and r.status == 200
    ):
        page.locator("#spaces-filter-active").select_option("true")
    expect(page.locator("#spaces-grid .space-card")).to_have_count(6)

    with page.expect_response(
        lambda r: r.url.endswith("/api/spaces") and r.status == 200
    ):
        page.locator("#spaces-filter-reset").click()
    expect(page.locator("#spaces-grid .space-card")).to_have_count(7)

    # Reactivar Sala Aura
    with page.expect_response(
        lambda r: f"/api/spaces/{aura_id}" in r.url
        and r.request.method == "PATCH"
        and r.status == 200
    ):
        page.locator(toggle_selector).click()
    expect(book_btn).to_be_enabled()
