from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

APP_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = APP_DIR / "reports"


def parse_args(argv: list[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    """Analiza los argumentos del lanzador y reenvia extras a pytest."""
    parser = argparse.ArgumentParser(
        description="Lanzador de la suite de pruebas automatizadas de AuraSpace."
    )
    parser.add_argument(
        "--suite",
        choices=("all", "unit", "integration", "e2e", "base"),
        default="all",
        help=(
            "Subconjunto de pruebas a ejecutar: all (todas), unit, integration, "
            "e2e o base (solo tests/test_auraspace.py)."
        ),
    )
    parser.add_argument(
        "--no-cov",
        action="store_true",
        help="Desactiva la medicion de cobertura de lineas y ramas con pytest-cov.",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Desactiva la generacion del reporte HTML con pytest-html.",
    )
    parser.add_argument(
        "--log",
        metavar="RUTA",
        default=None,
        help="Guarda la salida completa de la ejecucion en RUTA (codificacion UTF-8).",
    )
    return parser.parse_known_args(argv)


def build_pytest_command(args: argparse.Namespace, extra_args: list[str]) -> list[str]:
    """Construye la linea de comandos de pytest segun las opciones elegidas."""
    cmd: list[str] = [sys.executable, "-m", "pytest", "-v"]

    if args.suite == "base":
        cmd.append("tests/test_auraspace.py")
    elif args.suite in ("unit", "integration", "e2e"):
        cmd.extend(["-m", args.suite])

    if not args.no_cov:
        cmd.extend(
            [
                "--cov",
                "--cov-branch",
                "--cov-report=term-missing",
                "--cov-report=html:reports/htmlcov",
            ]
        )

    if not args.no_html:
        cmd.extend(
            [
                "--html=reports/test_report.html",
                "--self-contained-html",
            ]
        )

    if extra_args:
        cmd.extend(extra_args)

    return cmd


def _configure_console_streams() -> None:
    """Evita errores de codificacion en consolas Windows manteniendo UTF-8 cuando sea posible."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(errors="replace")
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada del lanzador CLI."""
    _configure_console_streams()
    args, extra_args = parse_args(argv)

    if not args.no_cov or not args.no_html:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    cmd = build_pytest_command(args, extra_args)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    if not args.log:
        completed = subprocess.run(cmd, cwd=APP_DIR, env=env, check=False)
        return int(completed.returncode)

    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("w", encoding="utf-8", newline="\n") as log_file:
        process = subprocess.Popen(
            cmd,
            cwd=APP_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log_file.write(line)
        return int(process.wait())


if __name__ == "__main__":
    raise SystemExit(main())
