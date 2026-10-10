"""Módulo de evaluación de contexto de negocio y supresión de señuelos."""
from datetime import datetime, time
from typing import Optional
from src.config import TENANTS_CONFIG


class BusinessContextManager:
    """Verifica si un momento temporal coincide con ventanas de negocio planificadas o respaldos."""

    def __init__(self, tenant: str):
        self.tenant = tenant
        self.cfg = TENANTS_CONFIG.get(tenant, {})
        self.senuelos = self.cfg.get("senuelos_programados", [])
        self.recurrentes = self.cfg.get("recurrentes_diarios", [])

        # Parsear fechas de señuelos programados
        self._ventanas_programadas = []
        for s in self.senuelos:
            ini = datetime.strptime(s["inicio"], "%Y-%m-%d %H:%M")
            fin = datetime.strptime(s["fin"], "%Y-%m-%d %H:%M")
            self._ventanas_programadas.append((ini, fin, s["tipo"]))

    def es_ventana_senuelo(self, ts: datetime) -> Optional[str]:
        """Devuelve el tipo de señuelo si ts cae en una ventana programada benigna, o None."""
        # 1. Chequeo de señuelos únicos programados
        for ini, fin, tipo in self._ventanas_programadas:
            if ini <= ts <= fin:
                return tipo

        # 2. Chequeo de respaldos recurrentes diarios
        t_actual = ts.time()
        for rec in self.recurrentes:
            h_ini = rec["hora_inicio"]
            # Convertir a minutos del día para manejar intervalos
            min_ini = h_ini.hour * 60 + h_ini.minute
            min_fin = min_ini + rec["duracion_min"]
            min_actual = t_actual.hour * 60 + t_actual.minute

            if min_ini <= min_actual <= min_fin:
                return rec["tipo"]

        return None
