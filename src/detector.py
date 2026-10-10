"""Motor de detección causal de alertas tempranas."""
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import deque
from itertools import islice
import math

from src.config import TENANTS_CONFIG
from src.context import BusinessContextManager
from src.preprocessor import TelemetryPreprocessor
from src.log_analyzer import CausalLogAnalyzer


class EarlyWarningDetector:
    """Procesa métricas y logs secuencialmente emitiendo alertas tempranas."""

    def __init__(self, tenant: str, ruta_tenant: Path):
        self.tenant = tenant
        self.ruta_tenant = ruta_tenant
        self.cfg = TENANTS_CONFIG[tenant]
        self.baseline = self.cfg["metricas_base"]

        self.context_mgr = BusinessContextManager(tenant)
        self.preprocessor = TelemetryPreprocessor(tenant, self.baseline)
        self.log_analyzer = CausalLogAnalyzer(ruta_tenant / "logs.md")

        # Buffer circular de métricas recientes (hasta 360 minutos = 6 horas)
        self.historial = deque(maxlen=360)

        # Control de cooldown de alertas para evitar duplicados del mismo incidente
        self.alertas_emitidas: List[Dict[str, Any]] = []
        self.cooldowns: Dict[str, datetime] = {}

    def _ultimos(self, campo: str, cantidad: int) -> List[float]:
        """Obtiene solo las últimas N observaciones, sin copiar todo el historial."""
        return [fila[campo] for fila in list(islice(reversed(self.historial), cantidad))[::-1]]

    def _calcular_pendiente(self, valores: List[float]) -> float:
        """Calcula la pendiente lineal simple dy/dx por minuto."""
        n = len(valores)
        if n < 5:
            return 0.0
        x_mean = (n - 1) / 2.0
        y_mean = sum(valores) / n
        numerador = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(valores))
        denominador = sum((i - x_mean) ** 2 for i in range(n))
        return numerador / denominador if denominador != 0 else 0.0

    def procesar_minuto(self, fila_cruda: Dict[str, Any], en_vivo: bool = False) -> Optional[Dict[str, Any]]:
        """Evalúa un minuto causalmente y retorna una alerta si se detecta un incidente."""
        fila = self.preprocessor.procesar_fila(fila_cruda)
        ts: datetime = fila["timestamp"]

        # Si el agente está en apagón total, no emitimos falsas alarmas
        if fila["es_apagon"]:
            self.historial.append(fila)
            return None

        # 1. Obtener logs causales hasta este minuto
        nuevos_logs = self.log_analyzer.obtener_eventos_hasta(ts)
        resultado_logs = self.log_analyzer.evaluar_senales_logs(nuevos_logs)

        # 2. Contexto de negocio: ¿Estamos en una ventana programada benigna?
        senuelo_activo = self.context_mgr.es_ventana_senuelo(ts)

        self.historial.append(fila)

        # Si estamos dentro de un señuelo programado y los logs confirman actividad benigna, suprimir
        if senuelo_activo and (resultado_logs["es_senuelo"] or not resultado_logs["precursores"]):
            return None

        # 3. Evaluar señales de logs precursores
        for tipo_inc, info_log in resultado_logs["precursores"].items():
            if self._esta_en_cooldown(tipo_inc, ts):
                continue

            confianza = 0.88
            alerta = self._emitir_alerta(ts, tipo_inc, confianza, en_vivo=en_vivo)
            if alerta:
                return alerta

        # 4. Análisis estadístico de métricas si hay suficiente historial (>= 60 min)
        if len(self.historial) >= 60:
            alerta_metrica = self._evaluar_anomalias_metricas(ts, senuelo_activo, en_vivo=en_vivo)
            if alerta_metrica:
                return alerta_metrica

        return None

    def _evaluar_anomalias_metricas(self, ts: datetime, senuelo_activo: Optional[str], en_vivo: bool = False) -> Optional[Dict[str, Any]]:
        """Detecta precursores por comportamiento físico de métricas."""
        # 1. Deriva persistente de disco (Gracko)
        if self.tenant == "gracko" and not self._esta_en_cooldown("deriva_disco", ts):
            if len(self.historial) >= 90:
                discos = self._ultimos("disco", 90)
                pendiente_disco = self._calcular_pendiente(discos)
                # Crecimiento sostenido > 0.03% por minuto (~1.8% por hora)
                if pendiente_disco > 0.03 and discos[-1] > (self.baseline["disco"] + 5.0):
                    if not senuelo_activo or senuelo_activo != "carga_masiva_declaraciones":
                        return self._emitir_alerta(ts, "deriva_disco", 0.82, en_vivo=en_vivo)

        # 2. Fuga de memoria RAM nocturna / fin de semana (Gramo)
        if self.tenant == "gramo" and not self._esta_en_cooldown("fuga_memoria_worker", ts):
            if len(self.historial) >= 90:
                rams = self._ultimos("ram", 90)
                pendiente_ram = self._calcular_pendiente(rams)
                if pendiente_ram > 0.035 and rams[-1] > (self.baseline["ram"] + 8.0):
                    return self._emitir_alerta(ts, "fuga_memoria_worker", 0.80, en_vivo=en_vivo)

        # 3. Crecimiento de memoria por caché GPS (TTR)
        if self.tenant == "ttr" and not self._esta_en_cooldown("crecimiento_cache_gps", ts):
            if len(self.historial) >= 120:
                rams = self._ultimos("ram", 120)
                pendiente_ram = self._calcular_pendiente(rams)
                if pendiente_ram > 0.025 and rams[-1] > (self.baseline["ram"] + 5.0):
                    return self._emitir_alerta(ts, "crecimiento_cache_gps", 0.78, en_vivo=en_vivo)

        # 4. Ráfaga brusca / Bot en checkout (Kaiku)
        if self.tenant == "kaiku" and not self._esta_en_cooldown("rafaga_bot_checkout", ts):
            if not senuelo_activo or senuelo_activo != "campana_correo":
                if len(self.historial) >= 15:
                    cpus = self._ultimos("cpu", 10)
                    latencias = self._ultimos("latencia_ms", 10)
                    cpu_reciente = sum(cpus) / len(cpus)
                    lat_reciente = sum(latencias) / len(latencias)
                    if cpu_reciente > (self.baseline["cpu"] + 25.0) and lat_reciente > (self.baseline["latencia"] + 150.0):
                        return self._emitir_alerta(ts, "rafaga_bot_checkout", 0.85, en_vivo=en_vivo)

        return None

    def _esta_en_cooldown(self, tipo_inc: str, ts: datetime) -> bool:
        """Evita alertar repetidamente para el mismo tipo de incidente en la corrida."""
        return tipo_inc in self.cooldowns

    def _emitir_alerta(self, ts: datetime, tipo_inc: str, confianza: float, en_vivo: bool = False) -> Dict[str, Any]:
        """Registra la alerta, establece el cooldown y notifica por SMS si es en vivo."""
        self.cooldowns[tipo_inc] = ts
        alerta = {
            "tenant": self.tenant,
            "timestamp": ts.isoformat(),
            "confianza": round(confianza, 2),
            "tipo_incidente": tipo_inc,
        }
        self.alertas_emitidas.append(alerta)
        if en_vivo:
            try:
                from src.notifier import notificar_incidencia_real
                notificar_incidencia_real(self.tenant, tipo_inc, confianza, ts.isoformat())
            except Exception as e:
                print(f"[!] Error enviando SMS Infobip: {e}")
        return alerta
