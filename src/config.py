"""Configuración de tenants, contexto de negocio, señuelos y patrones de incidentes."""
from datetime import time

TENANTS_CONFIG = {
    "gracko": {
        "nombre": "gracko",
        "giro": "Despacho contable y fiscal",
        "horario_laboral": {"dias": [0, 1, 2, 3, 4], "inicio": time(8, 0), "fin": time(18, 0)},
        "horario_sabado": {"dias": [5], "inicio": time(9, 0), "fin": time(13, 0)},
        "metricas_base": {"cpu": 26.0, "ram": 54.0, "disco": 58.0, "latencia": 40.0, "errores": 0.3},
        "senuelos_programados": [
            {"tipo": "carga_masiva_declaraciones", "inicio": "2026-10-09 17:00", "fin": "2026-10-09 19:40"},
            {"tipo": "cierre_nomina", "inicio": "2026-10-12 10:00", "fin": "2026-10-12 14:10"},
        ],
        "recurrentes_diarios": [
            {"tipo": "respaldo_nocturno", "hora_inicio": time(23, 0), "duracion_min": 45},
        ],
        "incidentes_esperados": ["deriva_disco", "cpu_intermitente_erp", "acceso_masivo_vpn"],
    },
    "gramo": {
        "nombre": "gramo",
        "giro": "Distribuidora de alimentos a restaurantes",
        "horario_laboral": {"dias": [0, 1, 2, 3, 4, 5], "inicio": time(7, 0), "fin": time(16, 0)},
        "metricas_base": {"cpu": 31.0, "ram": 55.0, "disco": 47.0, "latencia": 60.0, "errores": 0.5},
        "senuelos_programados": [
            {"tipo": "promo_2x1", "inicio": "2026-10-09 10:00", "fin": "2026-10-09 12:15"},
            {"tipo": "snapshot_inventario", "inicio": "2026-10-10 03:00", "fin": "2026-10-10 04:45"},
        ],
        "recurrentes_diarios": [
            {"tipo": "reporte_rutas_nocturno", "hora_inicio": time(2, 0), "duracion_min": 25},
        ],
        "incidentes_esperados": ["fuga_memoria_worker", "trafico_hostil_lento", "agotamiento_pool_inventario"],
    },
    "kaiku": {
        "nombre": "kaiku",
        "giro": "Comercio electrónico de café (24/7)",
        "horario_laboral": {"dias": [0, 1, 2, 3, 4, 5], "inicio": time(9, 0), "fin": time(19, 0)},
        "metricas_base": {"cpu": 30.0, "ram": 48.0, "disco": 44.0, "latencia": 60.0, "errores": 0.5},
        "senuelos_programados": [
            {"tipo": "campana_correo", "inicio": "2026-10-09 12:00", "fin": "2026-10-09 13:45"},
            {"tipo": "reindexado_catalogo", "inicio": "2026-10-11 04:00", "fin": "2026-10-11 05:40"},
        ],
        "recurrentes_diarios": [
            {"tipo": "mysqldump_diario", "hora_inicio": time(3, 0), "duracion_min": 35},
        ],
        "incidentes_esperados": ["saturacion_bd_gradual", "fuga_conexiones_checkout", "rafaga_bot_checkout"],
    },
    "ttr": {
        "nombre": "ttr",
        "giro": "Logística y transportes de última milla",
        "horario_laboral": {"dias": [0, 1, 2, 3, 4, 5], "inicio": time(6, 0), "fin": time(20, 0)},
        "metricas_base": {"cpu": 34.0, "ram": 61.0, "disco": 39.0, "latencia": 85.0, "errores": 0.4},
        "senuelos_programados": [
            {"tipo": "mantenimiento_red", "inicio": "2026-10-10 22:00", "fin": "2026-10-10 23:10"},
            {"tipo": "pedido_urgente", "inicio": "2026-10-13 06:00", "fin": "2026-10-13 09:10"},
        ],
        "recurrentes_diarios": [
            {"tipo": "respaldo_bd_nocturno", "hora_inicio": time(1, 0), "duracion_min": 50},
        ],
        "incidentes_esperados": ["crecimiento_cache_gps", "red_gps_intermitente", "bloqueo_base_rutas"],
    },
}

# Palabras clave y expresiones regulares en logs
PRECURSOR_LOG_PATTERNS = {
    # gracko
    "deriva_disco": [
        r"archivo nuevo en /data/tmp/exportaciones",
        r"exportacion masiva de expedientes en /data/tmp",
        r"disco /data al \d+% \(umbral 80%\)",
        r"volumen /data: \d+% usado",
    ],
    "cpu_intermitente_erp": [
        r"consulta de polizas tardo \d+ ms",
        r"ERP: consultas de polizas por encima de 3 s",
    ],
    "acceso_masivo_vpn": [
        r"VPN: usuario .* fallo la autenticacion",
        r"VPN: \d+ intentos fallidos en 10 min",
    ],
    # gramo
    "fuga_memoria_worker": [
        r"pedidos-worker: heap al \d+% tras lote nocturno",
        r"pedidos-worker: pausa de GC de",
        r"app-01: memoria RAM con tendencia ascendente",
    ],
    "trafico_hostil_lento": [
        r"conexiones 443/tcp por encima de lo habitual",
    ],
    "agotamiento_pool_inventario": [
        r"pool de conexiones a inventario al 85%",
    ],
    # kaiku
    "saturacion_bd_gradual": [
        r"consultas lentas registradas en srv-bd-01",
        r"pool de conexiones a la base de datos al 85%",
        r"cpu de srv-bd-01 al \d+% sostenido",
    ],
    "fuga_conexiones_checkout": [
        r"pool checkout: \d+ conexiones abiertas",
    ],
    "rafaga_bot_checkout": [
        r"pico de conexiones entrantes a 443/tcp \(x3 lo normal\)",
    ],
    # ttr
    "crecimiento_cache_gps": [
        r"cache de posiciones GPS en [\d\.]+ GB",
        r"cpu del optimizador de rutas al \d+% y en aumento",
    ],
    "red_gps_intermitente": [
        r"reconexion de \d+ unidades al rastreo GPS",
        r"posiciones de \d+ unidades sin datos >5 min",
    ],
    "bloqueo_base_rutas": [
        r"bd de rutas: espera de bloqueo de \d+ ms",
    ],
}

# Señuelos en logs para filtrar como benignos
DECOY_LOG_PATTERNS = [
    r"carga masiva de declaraciones en /data/declaraciones",
    r"cierre de nomina quincenal iniciado",
    r"promocion 2x1 en restaurantes activa",
    r"snapshot semanal de inventario iniciado",
    r"campana 'Otono de cafe'",
    r"reindexado del catalogo",
    r"ventana de mantenimiento de red en la sede",
    r"latencia de red elevada durante el mantenimiento",
    r"deadlock detectado en tabla productos \(transaccion reintentada\)",
    r"respaldo-nocturno: timeout de NAS en intento",
    r"mysqldump: espera de bloqueo de",
    r"respaldo de BD: 1 tabla omitida por bloqueo",
    r"planeacion extra completada",
    r"cola de calculo de rutas con 150 tareas pendientes",
]


