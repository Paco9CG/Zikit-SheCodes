"""Evaluador de benchmark local contra etiquetas de solución (Zero-dependency)."""
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple

from src.detector import EarlyWarningDetector
from src.preprocessor import TelemetryPreprocessor


class BenchmarkEvaluator:
    """Evalúa el desempeño del sistema de alerta temprana en corridas con solución."""

    def __init__(self, raiz_datos: Path):
        self.raiz_datos = raiz_datos

    def evaluar_corrida(self, carpeta_corrida: Path) -> Dict[str, Any]:
        """Ejecuta la detección causal en una corrida y calcula métricas."""
        carpeta_solucion = carpeta_corrida / "_solucion"
        if not carpeta_solucion.exists():
            raise FileNotFoundError(f"La carpeta {carpeta_corrida} no contiene _solucion")

        tenants = [d.name for d in carpeta_corrida.iterdir() if d.is_dir() and d.name != "_solucion"]
        todas_alertas = []
        incidentes_reales = []
        senuelos = []

        for tenant in tenants:
            ruta_tenant = carpeta_corrida / tenant
            ruta_metricas = ruta_tenant / "metricas.csv"

            # 1. Cargar etiquetas con csv estándar
            ruta_etiquetas = carpeta_solucion / tenant / "etiquetas.csv"
            with ruta_etiquetas.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    es_real = str(row["es_real"]).strip().lower() == "true"
                    ev = {
                        "tenant": tenant,
                        "timestamp": datetime.fromisoformat(row["inicio_incidente"]),
                        "tipo": row["tipo"],
                        "es_real": es_real,
                    }
                    if ev["es_real"]:
                        incidentes_reales.append(ev)
                    else:
                        senuelos.append(ev)

            # 2. Ejecutar detector minuto a minuto
            filas_crudo = TelemetryPreprocessor.cargar_metricas(ruta_metricas)
            detector = EarlyWarningDetector(tenant, ruta_tenant)

            for f in filas_crudo:
                alerta = detector.procesar_minuto(f)
                if alerta:
                    todas_alertas.append(alerta)

        # 3. Asociar alertas e incidentes de forma determinista, uno a uno.
        # Una alerta solo cuenta si ocurre antes del impacto, dentro de 72 h,
        # coincide en tenant y tipo, y el incidente aún no fue asignado.
        aciertos = []
        falsas_alarmas = []
        incidentes_detectados_ids = set()
        incidentes_reales.sort(key=lambda x: (x["timestamp"], x["tenant"], x["tipo"]))
        alertas_ordenadas = sorted(
            todas_alertas,
            key=lambda x: (datetime.fromisoformat(x["timestamp"]), x["tenant"], x.get("tipo_incidente", "")),
        )

        for alerta in alertas_ordenadas:
            t_alerta = datetime.fromisoformat(alerta["timestamp"])
            tipo_alerta = alerta.get("tipo_incidente")
            candidatos = []
            for idx, incidente in enumerate(incidentes_reales):
                if idx in incidentes_detectados_ids:
                    continue
                if incidente["tenant"] != alerta["tenant"]:
                    continue
                if tipo_alerta and tipo_alerta != incidente["tipo"]:
                    continue
                lead_min = (incidente["timestamp"] - t_alerta).total_seconds() / 60.0
                if 0 <= lead_min <= 72 * 60:
                    # Prioriza el impacto más cercano compatible para evitar
                    # que una alerta se asigne arbitrariamente a otro incidente.
                    candidatos.append((lead_min, idx, incidente))

            if candidatos:
                lead_min, idx, incidente = min(candidatos, key=lambda item: item[0])
                incidentes_detectados_ids.add(idx)
                aciertos.append({
                    "tenant": alerta["tenant"],
                    "tipo": incidente["tipo"],
                    "t_alerta": t_alerta,
                    "t_impacto": incidente["timestamp"],
                    "lead_time_min": int(lead_min),
                    "lead_time_horas": round(lead_min / 60.0, 2),
                    "confianza": alerta["confianza"],
                })
            else:
                falsas_alarmas.append({
                    "tenant": alerta["tenant"],
                    "timestamp": t_alerta,
                    "motivo": "falsa_alarma_o_duplicada",
                    "tipo": tipo_alerta,
                })

        tp = len(aciertos)
        fp = len(falsas_alarmas)
        fn = len(incidentes_reales) - tp

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        lead_times = [ac["lead_time_min"] for ac in aciertos]
        avg_lead_min = sum(lead_times) / len(lead_times) if lead_times else 0

        return {
            "corrida": carpeta_corrida.name,
            "total_incidentes_reales": len(incidentes_reales),
            "aciertos_tp": tp,
            "falsas_alarmas_fp": fp,
            "no_detectados_fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "lead_time_promedio_min": round(avg_lead_min, 1),
            "lead_time_promedio_horas": round(avg_lead_min / 60.0, 2),
            "detalle_aciertos": aciertos,
            "detalle_falsas_alarmas": falsas_alarmas,
            "senuelos_neutralizados": senuelos,
            "alertas_totales": todas_alertas,
        }