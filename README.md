# AuraSpace — Sistema de Gestión de Reservas de Coworking

Aplicación web **100 % offline** desarrollada con **Python 3 + Flask + SQLite (`sqlite3` estándar) + HTML5 / CSS3 / JavaScript Vanilla** para gestionar salas de coworking, agenda diaria por bloques horarios, reservas sin solapamientos, analítica operativa y exportación CSV, acompañada de una suite completa de **281 pruebas automatizadas en 3 niveles** (`unit`, `integration`, `e2e`) más compatibilidad con las 30 pruebas funcionales base.

---

## Reglas y alcance del proyecto

- **Ejecución 100 % offline**: sin CDNs externos (sin Bootstrap, Tailwind CDN, Chart.js ni Google Fonts). Toda la interfaz, iconos SVG (incluido `static/favicon.svg`), gráficos analíticos y estilos se sirven localmente desde Flask.
- **Alcance cerrado**: orientado a gestión operativa interna sin autenticación, login, gestión de usuarios, contraseñas ni envío de correos.
- **Consultas SQL parametrizadas**: todo acceso a SQLite utiliza marcadores `?` y `PRAGMA foreign_keys = ON`.
- **Horario comercial**: `08:00` a `21:00` en bloques de **30 minutos** (`:00` o `:30`), con duración mínima de **30 minutos** y máxima de **8 horas**.

---

## Funcionalidades principales

- **Catálogo de espacios (`Espacios`)**: listado de salas con filtros por texto (`q`), categoría, aforo mínimo y estado activo; tarjetas con equipamiento, tarifas por hora, botón de reserva rápida (deshabilitado en mantenimiento), alternancia de estado *Activa* / *Mantenimiento* y modal para dar de alta nuevos espacios.
- **Agenda diaria matricial (`Agenda Diaria`)**: selector de fecha con accesos rápidos (*Ayer*, *Hoy*, *Mañana*) y cuadrante *Sala × Horas (`08:00`–`21:00`)* con bloques proporcionales a hora de inicio y duración; clic en una reserva para editarla o clic en cualquier hueco libre para abrir el modal pre-rellenado.
- **Control transaccional de reservas (`Reservas`)**: modal de creación/edición con selector visual de los **26 bloques de 30 minutos** (`/api/availability`), cálculo en tiempo real de duración e importe, transacciones explícitas `BEGIN IMMEDIATE` que impiden dobles reservas (`HTTP 409 Conflict`), soporte para franjas contiguas exactas, cambio de estado (*confirmada*, *completada*, *cancelada*), validación de reactivaciones y exportación **CSV con BOM UTF-8 (`\ufeff`)** compatible con RFC 4180 y Excel.
- **Analítica nativa (`Analítica`)**: 4 tarjetas KPI (ingresos totales y del día, ocupación de la jornada, reservas confirmadas, completadas/canceladas) y **2 gráficos SVG** generados directamente con JavaScript Vanilla (ingresos por espacio y ocupación por franja horaria `08:00`–`20:00`).
- **Semilla inicial idempotente**: si la tabla `spaces` está vacía, el arranque crea automáticamente 6 salas de coworking y 14 reservas `AUR-*` relativas a `date.today()` (ayer completadas, hoy confirmadas + 1 cancelada y mañana confirmadas) sin solapamientos activos.

---

## Arquitectura y estructura actualizada del proyecto

Arquitectura por capas basada en 6 clases de dominio/datos/servicio y una suite QA estructurada en 3 niveles:

```text
auraspace/
├── models/
│   ├── __init__.py
│   ├── space.py                            # Clase Space (dataclass + to_dict / from_row)
│   └── booking.py                          # Clase Booking (dataclass + _parse_hhmm / duration_hours / to_dict / from_row)
├── database/
│   ├── __init__.py
│   └── db_manager.py                       # Clase DatabaseManager (esquema, índices, FKs y semilla idempotente)
├── repositories/
│   ├── __init__.py
│   ├── space_repository.py                 # Clase SpaceRepository (consultas parametrizadas de salas)
│   └── booking_repository.py               # Clase BookingRepository (consultas, solapamientos y persistencia)
├── services/
│   ├── __init__.py
│   └── reservation_service.py              # Clase ReservationService + DomainError / ValidationError / NotFoundError / ConflictError
├── templates/
│   └── index.html                          # Interfaz SPA con 4 vistas, modales, toasts y favicon local (sin CDNs)
├── static/
│   ├── style.css                           # Hoja de estilos clara (#F6F7F9) y verde petróleo (#0F766E)
│   ├── app.js                              # Lógica cliente JS Vanilla, escapeHtml() y gráficos SVG
│   └── favicon.svg                         # Icono SVG local (100 % offline)
├── scripts/
│   ├── setup_env.ps1                       # Instalador de entorno virtual y dependencias en Windows PowerShell
│   ├── setup_env.sh                        # Instalador de entorno virtual y dependencias en Linux / macOS
│   └── run_tests.py                        # Lanzador CLI (--suite, --no-cov, --no-html, --log)
├── tests/
│   ├── __init__.py
│   ├── conftest.py                         # Fixtures aisladas con tmp_path (BD vacía/sembrada y fábricas)
│   ├── test_auraspace.py                   # 30 pruebas funcionales base (RF-01 a RF-10)
│   ├── unit/                               # Nivel 1 (@pytest.mark.unit): 213 pruebas
│   │   ├── __init__.py
│   │   ├── test_models.py                  # Pruebas unitarias de Space y Booking
│   │   ├── test_database_manager.py        # Esquema, índices, semilla y restricciones DDL/FK/CHECK
│   │   ├── test_repositories.py            # SpaceRepository y BookingRepository
│   │   └── test_reservation_service_unit.py# Excepciones, validadores, límites y colisión de códigos
│   ├── integration/                        # Nivel 2 (@pytest.mark.integration): 28 pruebas
│   │   ├── __init__.py
│   │   ├── test_api_extended.py            # Contratos REST completos, reglas de negocio, analítica y CSV RFC 4180
│   │   └── test_concurrency_and_security.py# Concurrencia multi-hilo (Barrier), resistencia SQLi y errores HTTP JSON
│   └── e2e/                                # Nivel 3 (@pytest.mark.e2e): 10 pruebas en Microsoft Edge local
│       ├── __init__.py
│       ├── conftest.py                     # Servidor Werkzeug efímero + Playwright sobre Edge local
│       ├── test_ui_spaces_and_navigation.py# Carga limpia (0 errores HTTP/consola), 4 pestañas, filtros y mantenimiento
│       ├── test_ui_booking_and_schedule.py # Modal 26 bloques, tarifa en vivo, conflicto 409, Agenda y ciclo en tabla
│       └── test_ui_analytics_csv_security.py# KPIs, SVGs nativos, descarga real CSV con BOM y protección XSS
├── reports/                                # [Ignorado en Git] Reportes HTML generados por run_tests.py
│   ├── test_report.html                    # Reporte autocontenido de pytest-html
│   └── htmlcov/index.html                  # Reporte interactivo de cobertura de líneas y ramas (pytest-cov)
├── evidencias/                             # [Ignorado en Git] Logs UTF-8 de ejecuciones y evidencias QA
├── app.py                                  # Fábrica create_app(db_path=None, seed=True), API REST y errores JSON
├── pytest.ini                              # Configuración de pytest, pythonpath, strict-markers y marcadores
├── .coveragerc                             # Cobertura de líneas y ramas (branch = True) sobre código fuente
├── requirements.txt                        # Flask, pytest, pytest-cov, pytest-html y playwright
├── .gitignore
└── README.md
```

---

## Esquema SQLite y reglas de negocio

- **Tabla `spaces`**: `id` PK, `name` UNIQUE, `category`, `floor`, `capacity > 0`, `hourly_rate > 0`, `equipment`, `is_active IN (0, 1)`, `created_at`.
- **Tabla `bookings`**: `id` PK, `reference_code` UNIQUE (`AURA-YYYYMMDD-XXXX`), `space_id` FK `ON DELETE RESTRICT`, `title`, `customer_name`, `customer_email`, `attendees > 0`, `booking_date`, `start_time`, `end_time` (`CHECK (end_time > start_time)`), `total_price >= 0` (`round(duración_horas * hourly_rate, 2)`), `status IN ('confirmada', 'completada', 'cancelada')`, `notes`, `created_at`.
- **Índices**: `idx_bookings_space_date_status` sobre `(space_id, booking_date, status)` e `idx_bookings_date` sobre `(booking_date)`.

---

## Endpoints de la API REST

Todos los errores de la API devuelven JSON uniforme `{"error": "..."}` con códigos `400` (`ValidationError`), `404` (`NotFoundError` o ruta inexistente), `405` (método HTTP no permitido), `409` (`ConflictError`) y `500` (error interno del servidor sin exponer trazas ni HTML).

| Método y ruta | Descripción |
|---|---|
| `GET /` | Sirve `templates/index.html` |
| `GET /favicon.ico` | Sirve `static/favicon.svg` localmente sin depender de red |
| `GET /api/spaces` | Lista salas filtrables por `q`, `category`, `min_capacity` y `active_only` |
| `POST /api/spaces` | Crea una nueva sala de coworking (`201` / `409` si nombre duplicado) |
| `PATCH /api/spaces/<id>` | Cambia el estado operativo `is_active` de una sala |
| `GET /api/availability` | Devuelve los 26 bloques de 30 min (`08:00`–`21:00`) para `space_id` y `date` (soporta `exclude_booking_id` y marca todos como ocupados si la sala está inactiva) |
| `GET /api/schedule` | Devuelve todas las salas con sus reservas no canceladas de la fecha indicada |
| `GET /api/bookings` | Lista reservas enriquecidas con sala/planta filtrables por `q`, `space_id`, `status` y `date` |
| `POST /api/bookings` | Crea una reserva validando reglas y solapamientos bajo `BEGIN IMMEDIATE` |
| `PUT /api/bookings/<id>` | Edita una reserva activa recalculando tarifa y disponibilidad (prohibido si está cancelada) |
| `PATCH /api/bookings/<id>/status` | Cambia el estado (`confirmada`, `completada`, `cancelada`) validando sala activa y conflictos al reactivar |
| `GET /api/bookings/export` | Exporta las reservas filtradas en `text/csv; charset=utf-8` con BOM UTF-8 (`\ufeff`) |
| `GET /api/analytics` | Devuelve KPIs de ingresos, conteos por estado, ocupación y desglose por sala y por hora |

---

## Requisitos previos

- **Python 3.10 o superior** (verificado en **Python 3.14.6** con **Flask 3.1.3**, **pytest 9.2.0**, **pytest-cov 7.1.0**, **pytest-html 4.2.0** y **playwright 1.65.2**).
- **Microsoft Edge** (o navegador Chromium/Chrome compatible) instalado localmente para las pruebas E2E (`@pytest.mark.e2e`).
  - La configuración de Playwright en `tests/e2e/conftest.py` utiliza directamente el ejecutable local de Microsoft Edge (`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`, `C:\Program Files\Microsoft\Edge\Application\msedge.exe` o `msedge` en `PATH`), por lo que **no es necesario ejecutar `playwright install` ni descargar navegadores**.

---

## Instalación y ejecución en local

### Opción A: Instalación automatizada (recomendada)

#### Windows (PowerShell)

```powershell
cd auraspace

# Crea o reutiliza ..\.venv (un nivel arriba) e instala requirements.txt
.\scripts\setup_env.ps1

# Opcional: crear el entorno dentro de auraspace\.venv
.\scripts\setup_env.ps1 -Location local
```

#### Linux / macOS (Bash)

```bash
cd auraspace
chmod +x scripts/setup_env.sh

# Crea o reutiliza ../.venv (un nivel arriba) e instala requirements.txt
./scripts/setup_env.sh

# Opcional: crear el entorno dentro de auraspace/.venv
./scripts/setup_env.sh --local
```

### Opción B: Instalación manual

#### Windows (PowerShell)

```powershell
# Desde la raíz del repositorio (o dentro de auraspace/)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r auraspace\requirements.txt
```

#### Linux / macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r auraspace/requirements.txt
```

### Iniciar la aplicación web

```powershell
# Windows (desde auraspace/, usando ..\.venv)
cd auraspace
..\.venv\Scripts\python.exe app.py
```

```bash
# Linux / macOS (desde auraspace/, usando ../.venv)
cd auraspace
../.venv/bin/python app.py
```

Una vez iniciada, abre en el navegador **`http://127.0.0.1:5000`**.

---

## Ejecución de la suite de pruebas automatizadas

El lanzador [scripts/run_tests.py](scripts/run_tests.py) centraliza la ejecución de todos los niveles configurados en `pytest.ini` y `.coveragerc`. Por defecto ejecuta `pytest -v` con cobertura de líneas/ramas (`--cov --cov-branch`) y reporte HTML autocontenido (`--html=reports/test_report.html --self-contained-html`).

### Comandos por nivel (Windows PowerShell, desde `auraspace/`)

```powershell
# Suite base original (30 pruebas funcionales RF-01 a RF-10 en tests/test_auraspace.py)
..\.venv\Scripts\python.exe scripts\run_tests.py --suite base

# Nivel 1: Pruebas unitarias (213 pruebas)
..\.venv\Scripts\python.exe scripts\run_tests.py --suite unit

# Nivel 2: Pruebas de integración, concurrencia y seguridad (28 pruebas)
..\.venv\Scripts\python.exe scripts\run_tests.py --suite integration

# Nivel 3: Pruebas End-to-End en Microsoft Edge local (10 pruebas)
..\.venv\Scripts\python.exe scripts\run_tests.py --suite e2e

# Suite completa (281 pruebas: base + unit + integration + e2e) con cobertura y HTML
..\.venv\Scripts\python.exe scripts\run_tests.py --suite all

# Suite completa guardando log completo en UTF-8
..\.venv\Scripts\python.exe scripts\run_tests.py --suite all --log evidencias\02_pytest_completo_final.txt
```

### Comandos equivalentes en Linux / macOS (desde `auraspace/`)

```bash
../.venv/bin/python scripts/run_tests.py --suite base
../.venv/bin/python scripts/run_tests.py --suite unit
../.venv/bin/python scripts/run_tests.py --suite integration
../.venv/bin/python scripts/run_tests.py --suite e2e
../.venv/bin/python scripts/run_tests.py --suite all --log evidencias/02_pytest_completo_final.txt
```

### Opciones adicionales del lanzador

- `--no-cov`: omite la medición de cobertura con `pytest-cov` (ejecución más rápida).
- `--no-html`: omite la generación de `reports/test_report.html`.
- `--log RUTA`: muestra la salida en tiempo real y la guarda en `RUTA` con codificación UTF-8.
- Cualquier flag adicional de `pytest` (como `-k "patron"` o `--maxfail=1`) se reenvía directamente:
  ```powershell
  ..\.venv\Scripts\python.exe scripts\run_tests.py --suite e2e --no-cov --no-html -k "analytics"
  ```

---

## Cómo consultar los reportes HTML

Cada ejecución completa genera dos reportes locales dentro de `auraspace/reports/`:

1. **Reporte de resultados de pruebas (`pytest-html`)**: [`reports/test_report.html`](reports/test_report.html)
   - Contiene el detalle por caso, duración, metadatos del entorno y trazas.
2. **Reporte de cobertura de líneas y ramas (`pytest-cov`)**: [`reports/htmlcov/index.html`](reports/htmlcov/index.html)
   - Permite inspeccionar archivo por archivo las líneas ejecutadas, las líneas omitidas y las ramas parciales (`branch = True`).

Para abrirlos directamente desde la terminal (en `auraspace/`):

```powershell
# Windows PowerShell
Start-Process reports\test_report.html
Start-Process reports\htmlcov\index.html
```

```bash
# macOS / Linux
open reports/test_report.html reports/htmlcov/index.html      # macOS
xdg-open reports/test_report.html reports/htmlcov/index.html  # Linux
```

---

## Métricas reales finales obtenidas

Resultados registrados tras la ejecución completa final (`scripts/run_tests.py --suite all --log evidencias/02_pytest_completo_final.txt`) en **Python 3.14.6 / Windows 11**:

### Resumen por nivel de pruebas

| Nivel / Suite | Marcador / Archivo | Casos ejecutados | Resultado |
|---|---|---:|---|
| Pruebas funcionales base (RF-01 a RF-10) | `tests/test_auraspace.py` | 30 | **30 passed** |
| Nivel 1 — Pruebas unitarias | `@pytest.mark.unit` | 213 | **213 passed** |
| Nivel 2 — Integración, concurrencia y seguridad | `@pytest.mark.integration` | 28 | **28 passed** |
| Nivel 3 — End-to-End (Playwright + Edge local) | `@pytest.mark.e2e` | 10 | **10 passed** |
| **Total suite completa** | `--suite all` | **281** | **281 passed (0 failed) en 18.10 s** |

### Cobertura de código (líneas y ramas)

| Módulo / Archivo | Sentencias | Sin cubrir | Ramas | Ramas parciales | Cobertura combinada |
|---|---:|---:|---:|---:|---:|
| `models/` (`__init__.py`, `booking.py`, `space.py`) | 70 | 0 | 6 | 0 | **100.0 %** |
| `database/` (`__init__.py`, `db_manager.py`) | 60 | 0 | 10 | 0 | **100.0 %** |
| `repositories/` (`__init__.py`, `booking_repository.py`, `space_repository.py`) | 179 | 0 | 54 | 0 | **100.0 %** |
| `services/__init__.py` | 3 | 0 | 0 | 0 | **100.0 %** |
| `app.py` | 134 | 3 | 18 | 1 | **97.4 %** |
| `services/reservation_service.py` | 403 | 18 | 152 | 10 | **93.9 %** |
| **TOTAL** | **849** | **21** | **240** | **11** | **96.5 %** |

### Defectos reales detectados y corregidos mediante la suite

1. **`GET /api/availability` en salas en mantenimiento**: `ReservationService.get_availability()` marcaba los 26 bloques como disponibles en salas con `is_active = False`; corregido para bloquear los 26 slots (`available = False`, `occupied = True`).
2. **Reactivación `cancelada → completada` en sala inactiva**: `ReservationService.change_status()` solo validaba `space.is_active` al reactivar a `confirmada`; corregido para bloquear cualquier reactivación sobre salas en mantenimiento (`HTTP 400`).
3. **Cálculo de ocupación en `GET /api/analytics` con salas desactivadas**: el porcentaje de ocupación sumaba horas/reservas de salas inactivas sobre un denominador de solo salas activas (llegando a `107.7 %`); corregido para computar ocupación únicamente sobre salas activas (`<= 100.0 %`).
4. **Contrato JSON ante errores `500` inesperados**: `app.py` carecía de `@app.errorhandler(500)` y devolvía HTML por defecto; corregido para devolver JSON uniforme `{"error": "Error interno del servidor."}`.
5. **Error `404` en `/favicon.ico` durante la carga del navegador**: añadido `static/favicon.svg`, `<link rel="icon">` local en `templates/index.html` y ruta `@app.get("/favicon.ico")` en `app.py` manteniendo la operación 100 % offline.
