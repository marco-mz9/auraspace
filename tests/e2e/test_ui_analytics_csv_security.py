from __future__ import annotations

from collections.abc import Callable
import csv
import io
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.sync_api import expect
import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Page

pytestmark = pytest.mark.e2e


def test_analytics_kpis_and_native_svg_charts(
    page: Page,
    live_server: str,
    future_date_factory: Callable[[int], str],
) -> None:
    """Analítica muestra KPIs, ambos gráficos SVG nativos y actualiza al cambiar fecha."""
    page.goto(live_server, wait_until="networkidle")

    with page.expect_response(
        lambda r: "/api/analytics" in r.url and r.status == 200
    ):
        page.locator("#tab-analytics").click()
    expect(page.locator("#view-analytics")).to_be_visible()

    expect(page.locator("#kpi-total-revenue")).to_contain_text("€")
    expect(page.locator("#kpi-total-revenue")).not_to_have_text("0,00 €")
    expect(page.locator("#kpi-occupancy-today")).to_contain_text("%")
    expect(page.locator("#kpi-occupancy-today")).not_to_have_text("0%")

    space_svg = page.locator("#analytics-by-space svg")
    hour_svg = page.locator("#analytics-by-hour svg")
    expect(space_svg).to_be_visible()
    expect(hour_svg).to_be_visible()

    space_texts = space_svg.locator("text").all_text_contents()
    assert any("Sala Aura" in text for text in space_texts)

    hour_texts = set(hour_svg.locator("text").all_text_contents())
    assert {"0%", "25%", "50%", "75%", "100%"}.issubset(hour_texts)
    assert {"08h", "20h"}.issubset(hour_texts)

    # Cambiar a una fecha futura sin reservas muestra 0% de ocupación
    empty_date = future_date_factory(40)
    with page.expect_response(
        lambda r: "/api/analytics" in r.url
        and f"date={empty_date}" in r.url
        and r.status == 200
    ):
        page.locator("#analytics-date").fill(empty_date)
    expect(page.locator("#kpi-occupancy-today")).to_have_text("0%")

    with page.expect_response(
        lambda r: "/api/analytics" in r.url and r.status == 200
    ):
        page.locator("#analytics-today").click()
    expect(page.locator("#kpi-occupancy-today")).not_to_have_text("0%")


def test_csv_download_bom_and_filtered_rows(
    page: Page,
    live_server: str,
    tmp_path: Path,
) -> None:
    """Exportar CSV desde la UI descarga un archivo UTF-8 con BOM y respeta los filtros."""
    page.goto(live_server, wait_until="networkidle")

    with page.expect_response(
        lambda r: "/api/bookings" in r.url and r.status == 200
    ):
        page.locator("#tab-bookings").click()

    with page.expect_response(
        lambda r: "/api/bookings" in r.url
        and "status=completada" in r.url
        and r.status == 200
    ):
        page.locator("#bookings-filter-status").select_option("completada")
    expect(page.locator("#bookings-tbody tr")).to_have_count(4)

    with page.expect_download() as download_info:
        page.locator("#btn-export-csv").click()

    download = download_info.value
    assert download.suggested_filename == "auraspace_reservas.csv"
    saved_path = tmp_path / download.suggested_filename
    download.save_as(saved_path)

    raw_bytes = saved_path.read_bytes()
    assert raw_bytes.startswith(b"\xef\xbb\xbf")

    csv_text = raw_bytes.decode("utf-8")
    assert csv_text.startswith("\ufeff")

    rows = list(csv.reader(io.StringIO(csv_text.lstrip("\ufeff"))))
    assert len(rows) == 5  # Cabecera + 4 reservas completadas de la semilla
    headers, data_rows = rows[0], rows[1:]
    assert "Código" in headers
    assert "Importe (€)" in headers
    status_idx = headers.index("Estado")
    assert all(row[status_idx] == "completada" for row in data_rows)


def test_xss_payload_is_escaped_and_never_executes(
    page: Page,
    live_server: str,
    future_date_factory: Callable[[int], str],
) -> None:
    """Payloads XSS en título y cliente se muestran escapados sin ejecutar JavaScript."""
    xss_payload = '<img src=x onerror="window.__xss=true">'
    target_date = future_date_factory(25)

    page.goto(live_server, wait_until="networkidle")
    with page.expect_response(
        lambda r: "/api/availability" in r.url and r.status == 200
    ):
        page.locator("#btn-new-booking").click()

    with page.expect_response(
        lambda r: "/api/availability" in r.url
        and f"date={target_date}" in r.url
        and r.status == 200
    ):
        page.locator("#booking-date").fill(target_date)

    page.locator("#booking-title").fill(xss_payload)
    page.locator("#booking-customer-name").fill(xss_payload)
    page.locator("#booking-customer-email").fill("xss.check@empresa.es")
    page.locator("#booking-attendees").fill("2")

    with page.expect_response(
        lambda r: r.url.endswith("/api/bookings")
        and r.request.method == "POST"
        and r.status == 201
    ):
        page.locator("#booking-submit-btn").click()
    expect(page.locator("#booking-modal")).to_be_hidden()

    # Verificar escape en la tabla de Reservas
    with page.expect_response(
        lambda r: "/api/bookings" in r.url and r.status == 200
    ):
        page.locator("#tab-bookings").click()

    with page.expect_response(
        lambda r: "/api/bookings" in r.url
        and f"date={target_date}" in r.url
        and r.status == 200
    ):
        page.locator("#bookings-filter-date").fill(target_date)

    expect(page.locator("#bookings-tbody")).to_contain_text(xss_payload)
    assert page.locator("#bookings-tbody img").count() == 0
    assert page.evaluate("() => window.__xss ?? null") is None

    # Verificar escape en la Agenda Diaria
    with page.expect_response(
        lambda r: "/api/schedule" in r.url and r.status == 200
    ):
        page.locator("#tab-schedule").click()

    with page.expect_response(
        lambda r: "/api/schedule" in r.url
        and f"date={target_date}" in r.url
        and r.status == 200
    ):
        page.locator("#schedule-date").fill(target_date)

    expect(page.locator("#schedule-board")).to_contain_text(xss_payload)
    assert page.locator("#schedule-board img").count() == 0
    assert page.evaluate("() => window.__xss ?? null") is None
