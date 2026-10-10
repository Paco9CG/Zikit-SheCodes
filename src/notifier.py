"""Módulo de notificaciones SMS mediante Infobip v3 API (México)."""
import os
import sys
import json
import http.client
import urllib.request
import urllib.parse
from typing import Optional

def _normalizar_numero(num: str) -> str:
    """Normaliza un número de teléfono para Infobip (ej. 528713280948)."""
    num = (num or "").strip().lstrip("+")
    if not num:
        return ""
    if len(num) == 10:
        return f"52{num}"
    return num

# Cargar variables de entorno o valores por defecto del usuario
INFOBIP_BASE_URL = os.environ.get("INFOBIP_BASE_URL", "https://rkxxql.api.infobip.com")
INFOBIP_API_KEY = os.environ.get("INFOBIP_API_KEY", "828eda110660713d4d81444df737aeee-7df40830-5166-4903-a0bc-bb5af19bd6f4")
INFOBIP_SENDER = os.environ.get("INFOBIP_SENDER", "8711668582")
INFOBIP_TO = _normalizar_numero(os.environ.get("INFOBIP_TO", "528713280948"))

# Mapa de acciones sugeridas para solución inmediata según tipo de incidente
ACCIONES_SUGERIDAS = {
    "deriva_disco": "Ejecutar purga en /data/tmp y activar rotación de logs.",
    "fuga_memoria_worker": "Reiniciar workers de pedidos y ajustar recolección de basura (GC).",
    "saturacion_bd_gradual": "Escalar pool de conexiones a BD y optimizar consultas en srv-bd-01.",
    "crecimiento_cache_gps": "Vaciar caché de posiciones GPS y reiniciar optimizador de rutas.",
    "rafaga_bot_checkout": "Activar Rate Limiting y filtro WAF/bot en checkout.",
    "cpu_intermitente_erp": "Optimizar consultas de pólizas y aislar hilos del ERP.",
    "acceso_masivo_vpn": "Bloquear IPs con intentos fallidos en VPN y exigir 2FA.",
    "trafico_hostil_lento": "Activar protección WAF contra tráfico lento en 443/tcp.",
    "agotamiento_pool_inventario": "Aumentar max_connections en pool de inventario.",
    "fuga_conexiones_checkout": "Aplicar timeout a conexiones inactivas en checkout.",
    "red_gps_intermitente": "Revisar gateway de telecomunicaciones y reiniciar enlace GPS.",
    "bloqueo_base_rutas": "Liberar transacciones bloqueadas en la tabla de rutas.",
}


def enviar_sms_infobip(
    texto: str,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    sender: Optional[str] = None,
    to_num: Optional[str] = None
) -> Optional[str]:
    """Envía un SMS usando la API v3 de Infobip (/sms/3/messages)."""
    # Resolución dinámica de parámetros (soporta env vars o valores por defecto en tiempo de ejecución)
    target_url = (base_url or os.environ.get("INFOBIP_BASE_URL") or INFOBIP_BASE_URL or "https://rkxxql.api.infobip.com").strip()
    target_key = (api_key or os.environ.get("INFOBIP_API_KEY") or INFOBIP_API_KEY or "").strip()
    target_sender = (sender or os.environ.get("INFOBIP_SENDER") or INFOBIP_SENDER or "8711668582").strip()
    target_to = (to_num or os.environ.get("INFOBIP_TO") or INFOBIP_TO or "528713280948").strip()

    dest_num = _normalizar_numero(target_to)

    # Extraer host para HTTPSConnection
    host = target_url.replace("https://", "").replace("http://", "").split("/")[0]

    auth_header = target_key if target_key.startswith("App ") else f"App {target_key}"

    print(f"\n[📱 INFOBIP SMS v3] Procesando envío de alerta...", file=sys.stderr, flush=True)
    print(f"  ├─ Host: {host}", file=sys.stderr, flush=True)
    print(f"  ├─ Remitente (Sender): {target_sender}", file=sys.stderr, flush=True)
    print(f"  └─ Destinatario (To): {dest_num}", file=sys.stderr, flush=True)

    # 1. Envío mediante http.client.HTTPSConnection
    try:
        payload = json.dumps({
            "messages": [
                {
                    "destinations": [
                        {
                            "to": dest_num
                        }
                    ],
                    "sender": target_sender,
                    "content": {
                        "text": texto
                    }
                }
            ]
        })

        headers = {
            'Authorization': auth_header,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        conn = http.client.HTTPSConnection(host, timeout=10)
        conn.request("POST", "/sms/3/messages", payload, headers)
        res = conn.getresponse()
        data_bytes = res.read()
        conn.close()

        res_str = data_bytes.decode("utf-8", errors="ignore")
        if 200 <= res.status < 300:
            try:
                res_json = json.loads(res_str)
                messages = res_json.get("messages", [])
                msg_id = messages[0].get("messageId") if messages else res_json.get("bulkId", "OK")
            except Exception:
                msg_id = "OK"
            print(f"[+] SMS enviado con éxito vía Infobip v3 (HTTP {res.status}). MessageID: {msg_id}", file=sys.stderr, flush=True)
            return msg_id
        else:
            print(f"[!] Error HTTP Infobip ({res.status}): {res_str}", file=sys.stderr, flush=True)
            return None

    except Exception as err:
        print(f"[!] Error de conexión al enviar SMS vía Infobip HTTP: {err}", file=sys.stderr, flush=True)

    # 2. Fallback con urllib.request
    try:
        url = f"https://{host}/sms/3/messages"
        json_data = payload.encode("utf-8")
        req = urllib.request.Request(url, data=json_data, method="POST")
        req.add_header("Authorization", auth_header)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        with urllib.request.urlopen(req, timeout=10) as respuesta:
            res_json = json.loads(respuesta.read().decode("utf-8"))
            messages = res_json.get("messages", [])
            msg_id = messages[0].get("messageId") if messages else "OK"
            print(f"[+] SMS enviado con éxito vía Infobip urllib. MessageID: {msg_id}", file=sys.stderr, flush=True)
            return msg_id
    except urllib.error.HTTPError as err:
        try:
            err_body = err.read().decode("utf-8", errors="ignore")
            print(f"[!] Error HTTP Infobip urllib ({err.code}): {err_body}", file=sys.stderr, flush=True)
        except Exception:
            print(f"[!] Error HTTP Infobip urllib ({err.code}): {err}", file=sys.stderr, flush=True)
        return None
    except Exception as err:
        print(f"[!] Error fallback urllib Infobip: {err}", file=sys.stderr, flush=True)
        return None


def notificar_incidencia_real(tenant: str, tipo_incidente: str, confianza: float, timestamp: str) -> Optional[str]:
    """Construye y envía el mensaje de alerta temprana por SMS para incidencias reales con la acción sugerida."""
    accion_sugerida = ACCIONES_SUGERIDAS.get(
        tipo_incidente,
        "Ejecutar diagnóstico preventivo y revisar logs del servicio afectado."
    )
    mensaje = (
        f"🚨 ALERTA TEMPRANA [Zikit]\n"
        f"Tenant: {tenant.upper()}\n"
        f"Tipo: {tipo_incidente}\n"
        f"Confianza: {int(confianza * 100)}%\n"
        f"Timestamp: {timestamp}\n"
        f"💡 Acción Sugerida: {accion_sugerida}"
    )
    return enviar_sms_infobip(mensaje)
