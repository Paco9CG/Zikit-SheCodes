"""Módulo de análisis causal de logs."""
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple
from src.config import PRECURSOR_LOG_PATTERNS, DECOY_LOG_PATTERNS


class CausalLogAnalyzer:
    """Indexa y evalúa logs minuto a minuto sin mirar al futuro."""

    def __init__(self, ruta_logs: Path):
        self.logs = self._cargar_logs(ruta_logs)
        self.cursor = 0
        self.total = len(self.logs)

        # Compilar patrones regex
        self.patrones_precursores = {
            tipo: [re.compile(p, re.IGNORECASE) for p in pats]
            for tipo, pats in PRECURSOR_LOG_PATTERNS.items()
        }
        self.patrones_senuelos = [re.compile(p, re.IGNORECASE) for p in DECOY_LOG_PATTERNS]

    def _cargar_logs(self, ruta_logs: Path) -> List[Dict[str, Any]]:
        if not ruta_logs.exists():
            return []

        contenido = ruta_logs.read_text(encoding="utf-8")
        lineas = contenido.splitlines()

        registros = []
        fuente_actual = "general"
        regex_log = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\s+(\w+)\s+(.+)$")

        for l in lineas:
            l_strip = l.strip()
            if l_strip.startswith("## "):
                fuente_actual = l_strip.replace("## ", "").strip()
                continue
            match = regex_log.match(l_strip)
            if match:
                ts_str, nivel, mensaje = match.groups()
                ts = datetime.fromisoformat(ts_str)
                registros.append({
                    "timestamp": ts,
                    "fuente": fuente_actual,
                    "nivel": nivel,
                    "mensaje": mensaje,
                })

        registros.sort(key=lambda x: x["timestamp"])
        return registros

    def obtener_eventos_hasta(self, ts_actual: datetime) -> List[Dict[str, Any]]:
        """Avanza el cursor causalmente y retorna todos los logs nuevos hasta ts_actual."""
        nuevos = []
        while self.cursor < self.total and self.logs[self.cursor]["timestamp"] <= ts_actual:
            nuevos.append(self.logs[self.cursor])
            self.cursor += 1
        return nuevos

    def evaluar_senales_logs(self, logs_recientes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Evalúa los logs recientes buscando pistas precursoras de incidentes reales o señuelos."""
        precursores_detectados = {}
        es_senuelo = False
        senuelo_razon = None

        for log in logs_recientes:
            msg = log["mensaje"]

            # 1. Comprobar si es un mensaje de señuelo conocido
            for p_sen in self.patrones_senuelos:
                if p_sen.search(msg):
                    es_senuelo = True
                    senuelo_razon = msg
                    break

            # 2. Comprobar si coincide con un precursor de incidente
            for tipo_inc, regex_list in self.patrones_precursores.items():
                for rgx in regex_list:
                    if rgx.search(msg):
                        precursores_detectados[tipo_inc] = {
                            "timestamp": log["timestamp"],
                            "mensaje": msg,
                            "fuente": log["fuente"],
                            "nivel": log["nivel"],
                        }

        return {
            "precursores": precursores_detectados,
            "es_senuelo": es_senuelo,
            "senuelo_razon": senuelo_razon,
        }
