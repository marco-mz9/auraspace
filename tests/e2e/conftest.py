from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import shutil
import threading
from typing import TYPE_CHECKING

from playwright.sync_api import sync_playwright
import pytest
from werkzeug.serving import make_server

from app import create_app

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page


def _find_local_edge_executable() -> str:
    """Localiza el ejecutable de Microsoft Edge instalado en el sistema."""
    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    for binary in ("msedge", "microsoft-edge"):
        found = shutil.which(binary)
        if found:
            return found

    raise RuntimeError(
        "No se encontró Microsoft Edge instalado localmente para ejecutar las pruebas E2E."
    )


@pytest.fixture()
def live_server(tmp_path: Path) -> Iterator[str]:
    """Arranca AuraSpace en un hilo daemon sobre puerto efímero y BD temporal aislada."""
    flask_app = create_app(db_path=tmp_path / "e2e.db", seed=True)
    server = make_server("127.0.0.1", 0, flask_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    """Abre Microsoft Edge local en modo headless usando Playwright sin descargar navegadores."""
    edge_path = _find_local_edge_executable()
    with sync_playwright() as pw:
        edge_browser = pw.chromium.launch(
            executable_path=edge_path,
            headless=True,
        )
        try:
            yield edge_browser
        finally:
            edge_browser.close()


@pytest.fixture()
def page(browser: Browser) -> Iterator[Page]:
    """Crea un contexto y página aislados (1440x920) verificando 0 errores JS no capturados."""
    context = browser.new_context(
        viewport={"width": 1440, "height": 920},
        accept_downloads=True,
    )
    pw_page = context.new_page()
    pw_page.set_default_timeout(10_000)

    pageerrors: list[str] = []
    pw_page.on("pageerror", lambda err: pageerrors.append(str(err)))

    try:
        yield pw_page
    finally:
        context.close()
        assert pageerrors == [], f"Se detectaron errores JS en página: {pageerrors}"
