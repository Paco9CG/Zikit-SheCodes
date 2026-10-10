"""Preprocesamiento causal y robusto de telemetría."""
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
import csv
import math


class TelemetryPreprocessor:
    """Limpia una fila en tiempo t sin utilizar observaciones posteriores a t."""

    COLUMNAS = ("cpu", "ram", "disco", "latencia_ms", "errores")

    def __init__(self, tenant: str, baseline: Dict[str, float]):
        self.tenant = tenant
        self.baseline = baseline
        self.ultimo_valor = {
            col: float(baseline.get("latencia" if col == "latencia_ms" else col, 0.0))
            for col in self.COLUMNAS
        }
        self.consecutivos_nulos = 0
        self.en_apagon = False

    def procesar_fila(self, fila_cruda: Dict[str, Any]) -> Dict[str, Any]:
        if "timestamp" not in fila_cruda or not fila_cruda["timestamp"]:
            raise ValueError("La fila de métricas no contiene timestamp")
        ts = fila_cruda["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.strip())

        nulos = 0
        valores = {"timestamp": ts}
        for col in self.COLUMNAS:
            raw = fila_cruda.get(col)
            try:
                valor = float(raw) if raw is not None and str(raw).strip() != "" else math.nan
            except (ValueError, TypeError):
                valor = math.nan
            if not math.isfinite(valor):
                nulos += 1
                valor = self.ultimo_valor[col]  
            else:
                self.ultimo_valor[col] = valor
            valores[col] = valor

        if nulos >= len(self.COLUMNAS) - 1:
            self.consecutivos_nulos += 1
        else:
            self.consecutivos_nulos = 0
        self.en_apagon = self.consecutivos_nulos >= 3
        valores["es_apagon"] = self.en_apagon
        valores["campos_nulos"] = nulos
        return valores

    @staticmethod
    def cargar_metricas(ruta_csv: Path) -> List[Dict[str, Any]]:
        """Carga CSV respetando encabezados y celdas vacías."""
        filas: List[Dict[str, Any]] = []
        with ruta_csv.open("r", encoding="utf-8-sig", newline="") as archivo:
            reader = csv.DictReader(archivo)
            if not reader.fieldnames or "timestamp" not in reader.fieldnames:
                raise ValueError(f"CSV sin columna timestamp: {ruta_csv}")
            for numero, row in enumerate(reader, start=2):
                if not row or not row.get("timestamp"):
                    continue
                filas.append({
                    str(k).strip(): (v.strip() if isinstance(v, str) and v.strip() else None)
                    for k, v in row.items() if k is not None
                })
        return filas


