# AuraSpace — Sistema de Gestión de Reservas de Coworking

Aplicación web **100 % offline** desarrollada con **Python 3 + Flask + SQLite (`sqlite3` estándar) + HTML5 / CSS3 / JavaScript Vanilla** para gestionar salas de coworking, agenda diaria por bloques horarios, reservas sin solapamientos, analítica operativa y exportación CSV.

---

## Reglas y alcance del proyecto

- **Ejecución 100 % offline**: sin CDNs externos (sin Bootstrap, Tailwind CDN, Chart.js ni Google Fonts). Toda la interfaz, iconos SVG, gráficos analíticos y estilos se sirven localmente desde Flask.
- **Alcance cerrado**: orientado a gestión operativa interna sin autenticación, login, gestión de usuarios, contraseñas ni envío de correos.
- **Consultas SQL parametrizadas**: todo acceso a SQLite utiliza marcadores `?` y `PRAGMA foreign_keys = ON`.
- **Horario comercial**: `08:00` a `21:00` en bloques de **30 minutos** (`:00` o `:30`), con duración mínima de **30 minutos** y máxima de **8 horas**.

---

## Funcionalidades principales

- **Catálogo de espacios (`Espacios`)**: listado de salas con filtros por texto (`q`), categoría, aforo mínimo y estado activo; tarjetas con equipamiento, tarifas por hora, botón de reserva rápida (deshabilitado en mantenimiento), alternancia de estado *Activa* / *Mantenimiento* y modal para dar de alta nuevos espacios.
- **Agenda diaria matricial (`Agenda Diaria`)**: selector de fecha con accesos rápidos (*Ayer*, *Hoy*, *Mañana*) y cuadrante *Sala × Horas (`08:00`–`21:00`)* con bloques proporcionales a hora de inicio y duración; clic en una reserva para editarla o clic en cualquier hueco libre para abrir el modal pre-rellenado.
- **Control transaccional de reservas (`Reservas`)**: modal de creación/edición con selector visual de los **26 bloques de 30 minutos** (`/api/availability`), cálculo en tiempo real de duración e importe, transacciones explícitas `BEGIN IMMEDIATE` que impiden dobles reservas (`HTTP 409 Conflict`), soporte para franjas contiguas exactas, cambio de estado (*confirmada*, *completada*, *cancelada*), validación de reactivaciones y exportación **CSV con BOM UTF-8 (`\ufeff`)** para Excel.
- **Analítica nativa (`Analítica`)**: 4 tarjetas KPI (ingresos totales y del día, ocupación de la jornada, reservas confirmadas, completadas/canceladas) y **2 gráficos SVG** generados directamente con JavaScript Vanilla (ingresos por espacio y ocupación por franja horaria `08:00`–`20:00`).
- **Semilla inicial idempotente**: si la tabla `spaces` está vacía, el arranque crea automáticamente 6 salas de coworking y 14 reservas relativas a `date.today()` (ayer completadas, hoy confirmadas + 1 cancelada y mañana confirmadas) sin solapamientos activos.

---

## Arquitectura y estructura del proyecto

Arquitectura por capas basada en 6 clases de dominio/datos/servicio:

```text
auraspace/
├── models/
│   ├── __init__.py
│   ├── space.py                 # Clase Space (dataclass + to_dict / from_row)
│   └── booking.py               # Clase Booking (dataclass + duration_hours / to_dict / from_row)
├── database/
│   ├── __init__.py
│   └── db_manager.py            # Clase DatabaseManager (esquema, índices, conexión y semilla)
├── repositories/
│   ├── __init__.py
│   ├── space_repository.py      # Clase SpaceRepository (consultas parametrizadas de salas)
│   └── booking_repository.py    # Clase BookingRepository (consultas, solapamientos y persistencia)
├── services/
│   ├── __init__.py
│   └── reservation_service.py   # Clase ReservationService + ValidationError/NotFoundError/ConflictError
├── templates/
│   └── index.html               # Interfaz SPA con 4 vistas, modales y toasts (sin CDNs)
├── static/
│   ├── style.css                # Hoja de estilos clara (#F6F7F9) y verde petróleo (#0F766E)
│   └── app.js                   # Lógica cliente JS Vanilla, escapeHtml() y gráficos SVG
├── tests/
│   └── test_auraspace.py        # Suite de 30 pruebas con pytest (RF-01 a RF-10)
├── app.py                       # Fábrica create_app(db_path=None) y API REST Flask
├── requirements.txt             # Dependencias: Flask y pytest
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

Todos los errores de negocio devuelven JSON uniforme `{"error": "..."}` con códigos `400` (`ValidationError`), `404` (`NotFoundError`) y `409` (`ConflictError`).

| Método y ruta | Descripción |
|---|---|
| `GET /` | Sirve `templates/index.html` |
| `GET /api/spaces` | Lista salas filtrables por `q`, `category`, `min_capacity` y `active_only` |
| `POST /api/spaces` | Crea una nueva sala de coworking (`201` / `409` si nombre duplicado) |
| `PATCH /api/spaces/<id>` | Cambia el estado operativo `is_active` de una sala |
| `GET /api/availability` | Devuelve los 26 bloques de 30 min (`08:00`–`21:00`) para `space_id` y `date` (soporta `exclude_booking_id`) |
| `GET /api/schedule` | Devuelve todas las salas con sus reservas no canceladas de la fecha indicada |
| `GET /api/bookings` | Lista reservas enriquecidas con sala/planta filtrables por `q`, `space_id`, `status` y `date` |
| `POST /api/bookings` | Crea una reserva validando reglas y solapamientos bajo `BEGIN IMMEDIATE` |
| `PUT /api/bookings/<id>` | Edita una reserva activa recalculando tarifa y disponibilidad (prohibido si está cancelada) |
| `PATCH /api/bookings/<id>/status` | Cambia el estado (`confirmada`, `completada`, `cancelada`) validando conflictos al reactivar |
| `GET /api/bookings/export` | Exporta las reservas filtradas en `text/csv; charset=utf-8` con BOM UTF-8 (`\ufeff`) |
| `GET /api/analytics` | Devuelve KPIs de ingresos, conteos por estado, ocupación y desglose por sala y por hora |

---

## Requisitos previos

- **Python 3.10 o superior** (verificado con **Python 3.14.6** y **Flask 3.1.3**).

---

## Instalación y ejecución en local

### En Windows (PowerShell)

```powershell
# 1. Crear entorno virtual (si no existe en el repositorio)
python -m venv .venv

# 2. Instalar dependencias
.\.venv\Scripts\pip.exe install -r auraspace\requirements.txt

# 3. Iniciar la aplicación
cd auraspace
..\.venv\Scripts\python.exe app.py
```

### En Linux / macOS

```bash
# 1. Crear entorno virtual
python3 -m venv .venv

# 2. Instalar dependencias
.venv/bin/pip install -r auraspace/requirements.txt

# 3. Iniciar la aplicación
cd auraspace
../.venv/bin/python app.py
```

Una vez iniciada, abre en el navegador: **`http://127.0.0.1:5000`**.

---

## Ejecución de pruebas automatizadas

La suite `tests/test_auraspace.py` contiene **30 pruebas en `pytest`** sobre bases de datos SQLite temporales aisladas por test (`tmp_path` + `create_app(db_path=...)`), verificando de extremo a extremo los requisitos funcionales **RF-01 a RF-10**:

```powershell
# Desde la carpeta auraspace/ (Windows)
..\.venv\Scripts\pytest.exe -v

# O desde la raíz del repositorio
.\.venv\Scripts\pytest.exe -v auraspace\tests\test_auraspace.py
```

```bash
# Linux / macOS (desde auraspace/)
../.venv/bin/pytest -v
```
