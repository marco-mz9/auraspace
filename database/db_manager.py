from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sqlite3


class DatabaseManager:
    """Gestiona la conexión, el esquema y los datos iniciales de SQLite."""

    def __init__(self, db_path: str | Path = "auraspace.db") -> None:
        """Inicializa el gestor con la ruta de la base de datos SQLite."""
        self.db_path: str = str(db_path)
        if self.db_path != ":memory:" and not self.db_path.startswith("file:"):
            parent = Path(self.db_path).parent
            if str(parent) not in ("", "."):
                parent.mkdir(parents=True, exist_ok=True)

    def get_connection(
        self, isolation_level: str | None = "DEFERRED"
    ) -> sqlite3.Connection:
        """Abre una conexión SQLite con claves foráneas y row_factory activados."""
        conn = sqlite3.connect(self.db_path, isolation_level=isolation_level)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        """Crea las tablas e índices del esquema si todavía no existen."""
        conn = self.get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS spaces (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        category TEXT NOT NULL,
                        floor TEXT NOT NULL,
                        capacity INTEGER NOT NULL CHECK (capacity > 0),
                        hourly_rate REAL NOT NULL CHECK (hourly_rate > 0),
                        equipment TEXT NOT NULL DEFAULT '',
                        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bookings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        reference_code TEXT NOT NULL UNIQUE,
                        space_id INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        customer_name TEXT NOT NULL,
                        customer_email TEXT NOT NULL,
                        attendees INTEGER NOT NULL CHECK (attendees > 0),
                        booking_date TEXT NOT NULL,
                        start_time TEXT NOT NULL,
                        end_time TEXT NOT NULL,
                        total_price REAL NOT NULL CHECK (total_price >= 0),
                        status TEXT NOT NULL DEFAULT 'confirmada'
                            CHECK (status IN ('confirmada', 'completada', 'cancelada')),
                        notes TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        CHECK (end_time > start_time),
                        FOREIGN KEY (space_id) REFERENCES spaces(id) ON DELETE RESTRICT
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_bookings_space_date_status
                    ON bookings (space_id, booking_date, status);
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_bookings_date
                    ON bookings (booking_date);
                    """
                )
        finally:
            conn.close()

    @staticmethod
    def _hours_between(start_time: str, end_time: str) -> float:
        """Calcula las horas transcurridas entre dos horas en formato HH:MM."""
        start_hour, start_min = map(int, start_time.split(":"))
        end_hour, end_min = map(int, end_time.split(":"))
        return ((end_hour * 60 + end_min) - (start_hour * 60 + start_min)) / 60

    def seed_initial_data(self) -> bool:
        """Inserta salas y reservas de ejemplo de forma idempotente si no hay salas."""
        conn = self.get_connection()
        try:
            with conn:
                count_row = conn.execute(
                    "SELECT COUNT(*) AS total FROM spaces;"
                ).fetchone()
                if count_row is not None and int(count_row["total"]) > 0:
                    return False

                spaces_seed = [
                    (
                        "Sala Aura",
                        "Sala de reuniones",
                        "Planta 1",
                        8,
                        35.0,
                        'Pantalla 4K 65", Videoconferencia, Pizarra de cristal, Wi-Fi 6',
                        1,
                    ),
                    (
                        "Estudio Zenith",
                        "Sala de reuniones",
                        "Planta 2",
                        12,
                        50.0,
                        "Proyector láser, Sistema de audio, Pizarra magnética, Cafetera",
                        1,
                    ),
                    (
                        "Cabina Focus A",
                        "Cabina individual",
                        "Planta 1",
                        2,
                        14.0,
                        'Aislamiento acústico, Monitor 27", Iluminación regulable, USB-C',
                        1,
                    ),
                    (
                        "Oficina Privada Nova",
                        "Oficina privada",
                        "Planta 3",
                        6,
                        42.0,
                        "Escritorios ergonómicos, Monitor dual, Armarios con llave, Wi-Fi 6",
                        1,
                    ),
                    (
                        "Auditorio Horizonte",
                        "Auditorio",
                        "Planta Baja",
                        40,
                        120.0,
                        "Escenario, Proyector HD, 2 micrófonos inalámbricos, Streaming",
                        1,
                    ),
                    (
                        "Taller Creativo Brisa",
                        "Zona creativa",
                        "Planta 2",
                        16,
                        60.0,
                        'Mesas modulares, 3 pizarras móviles, Kit de prototipado, TV 55"',
                        1,
                    ),
                ]

                space_map: dict[str, tuple[int, float]] = {}
                for space_data in spaces_seed:
                    cursor = conn.execute(
                        """
                        INSERT INTO spaces (
                            name, category, floor, capacity, hourly_rate, equipment, is_active
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?);
                        """,
                        space_data,
                    )
                    assert cursor.lastrowid is not None
                    space_map[space_data[0]] = (int(cursor.lastrowid), space_data[4])

                today = date.today()
                yesterday = (today - timedelta(days=1)).isoformat()
                today_str = today.isoformat()
                tomorrow = (today + timedelta(days=1)).isoformat()

                bookings_seed = [
                    (
                        "Sala Aura",
                        "Comité semanal de producto",
                        "Lucía Fernández",
                        "lucia.fernandez@novatech.es",
                        6,
                        yesterday,
                        "09:00",
                        "11:00",
                        "completada",
                        "Revisión de hoja de ruta Q4.",
                    ),
                    (
                        "Estudio Zenith",
                        "Workshop de arquitectura cloud",
                        "Carlos Mendoza",
                        "carlos.mendoza@alquimia.io",
                        10,
                        yesterday,
                        "10:00",
                        "12:30",
                        "completada",
                        "Requiere adaptador HDMI en mesa.",
                    ),
                    (
                        "Cabina Focus A",
                        "Entrevista técnica backend",
                        "Elena Navarro",
                        "elena.navarro@talentoplus.es",
                        1,
                        yesterday,
                        "13:00",
                        "14:30",
                        "completada",
                        "Sesión remota sin interrupciones.",
                    ),
                    (
                        "Auditorio Horizonte",
                        "Demo Day FinTech Madrid",
                        "Javier Ortega",
                        "javier.ortega@impulsa.org",
                        32,
                        yesterday,
                        "16:00",
                        "18:30",
                        "completada",
                        "Grabación en streaming activada.",
                    ),
                    (
                        "Sala Aura",
                        "Daily ampliada de diseño",
                        "Marta Ruiz",
                        "marta.ruiz@pixelcraft.es",
                        5,
                        today_str,
                        "08:30",
                        "10:00",
                        "confirmada",
                        "Presentación de prototipos.",
                    ),
                    (
                        "Sala Aura",
                        "Negociación con proveedor",
                        "Diego Paredes",
                        "diego.paredes@logisur.com",
                        7,
                        today_str,
                        "11:00",
                        "13:00",
                        "confirmada",
                        "Se solicita café y agua para 7 personas.",
                    ),
                    (
                        "Estudio Zenith",
                        "Planificación sprint 14",
                        "Sofía Morales",
                        "sofia.morales@cloudia.es",
                        9,
                        today_str,
                        "09:30",
                        "11:30",
                        "confirmada",
                        "Uso de pizarra magnética y post-its.",
                    ),
                    (
                        "Cabina Focus A",
                        "Llamada de seguimiento cliente",
                        "Andrés Gil",
                        "andres.gil@consultora.es",
                        2,
                        today_str,
                        "10:00",
                        "11:00",
                        "confirmada",
                        "Reunión confidencial con dirección.",
                    ),
                    (
                        "Oficina Privada Nova",
                        "Jornada equipo jurídico",
                        "Patricia Vega",
                        "patricia.vega@lexdigital.es",
                        4,
                        today_str,
                        "14:00",
                        "17:30",
                        "confirmada",
                        "Acceso con tarjetas temporales en recepción.",
                    ),
                    (
                        "Taller Creativo Brisa",
                        "Sesión de ideación branding",
                        "Hugo Serrano",
                        "hugo.serrano@estudiobrava.es",
                        12,
                        today_str,
                        "16:00",
                        "18:00",
                        "cancelada",
                        "Cancelada por reprogramación del cliente.",
                    ),
                    (
                        "Sala Aura",
                        "Revisión trimestral de ventas",
                        "Beatriz Castro",
                        "beatriz.castro@ventaglobal.es",
                        6,
                        tomorrow,
                        "09:00",
                        "10:30",
                        "confirmada",
                        "Conexión con delegación de Barcelona.",
                    ),
                    (
                        "Estudio Zenith",
                        "Formación interna de ciberseguridad",
                        "Raúl Domínguez",
                        "raul.dominguez@shieldnet.es",
                        11,
                        tomorrow,
                        "12:00",
                        "14:00",
                        "confirmada",
                        "Proyector configurado antes de las 12:00.",
                    ),
                    (
                        "Taller Creativo Brisa",
                        "Design Sprint: onboarding móvil",
                        "Clara Iglesias",
                        "clara.iglesias@orbitapp.io",
                        14,
                        tomorrow,
                        "15:00",
                        "18:00",
                        "confirmada",
                        "Disposición de mesas en tres islas.",
                    ),
                    (
                        "Auditorio Horizonte",
                        "Mesa redonda IA aplicada",
                        "Fernando León",
                        "fernando.leon@forotech.es",
                        28,
                        tomorrow,
                        "17:00",
                        "19:30",
                        "confirmada",
                        "Dos micrófonos de mano y atril.",
                    ),
                ]

                for index, item in enumerate(bookings_seed, start=1):
                    (
                        space_name,
                        title,
                        customer_name,
                        customer_email,
                        attendees,
                        booking_date,
                        start_time,
                        end_time,
                        status,
                        notes,
                    ) = item
                    space_id, hourly_rate = space_map[space_name]
                    duration_hours = self._hours_between(start_time, end_time)
                    total_price = round(duration_hours * hourly_rate, 2)
                    reference_code = f"AUR-{booking_date.replace('-', '')}-{index:04d}"

                    conn.execute(
                        """
                        INSERT INTO bookings (
                            reference_code, space_id, title, customer_name,
                            customer_email, attendees, booking_date, start_time,
                            end_time, total_price, status, notes
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            reference_code,
                            space_id,
                            title,
                            customer_name,
                            customer_email,
                            attendees,
                            booking_date,
                            start_time,
                            end_time,
                            total_price,
                            status,
                            notes,
                        ),
                    )
                return True
        finally:
            conn.close()
