import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.preprocessor import TelemetryPreprocessor
from src.log_analyzer import CausalLogAnalyzer
from src.config import TENANTS_CONFIG


class PreprocessorTests(unittest.TestCase):
    def test_imputa_latencia_con_baseline_correcto(self):
        pre = TelemetryPreprocessor("gracko", TENANTS_CONFIG["gracko"]["metricas_base"])
        fila = pre.procesar_fila({
            "timestamp": "2026-10-08T08:00:00",
            "cpu": "", "ram": "", "disco": "", "latencia_ms": "", "errores": ""
        })
        self.assertEqual(fila["latencia_ms"], 40.0)
        self.assertFalse(fila["es_apagon"])

    def test_detecta_apagon_solo_despues_de_tres_filas_muy_incompletas(self):
        pre = TelemetryPreprocessor("gracko", TENANTS_CONFIG["gracko"]["metricas_base"])
        for minuto in range(2):
            fila = pre.procesar_fila({
                "timestamp": f"2026-10-08T08:0{minuto}:00",
                "cpu": "", "ram": "", "disco": "", "latencia_ms": "", "errores": ""
            })
            self.assertFalse(fila["es_apagon"])
        fila = pre.procesar_fila({
            "timestamp": "2026-10-08T08:02:00",
            "cpu": "", "ram": "", "disco": "", "latencia_ms": "", "errores": ""
        })
        self.assertTrue(fila["es_apagon"])


class CausalLogTests(unittest.TestCase):
    def test_no_entrega_logs_futuros(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "logs.md"
            ruta.write_text(
                "## servidor\n"
                "2026-10-08T08:00:10 INFO sesion abierta\n"
                "2026-10-08T09:00:10 ERROR pool de conexiones a la base de datos al 85%\n",
                encoding="utf-8",
            )
            analyzer = CausalLogAnalyzer(ruta)
            logs = analyzer.obtener_eventos_hasta(datetime.fromisoformat("2026-10-08T08:30:00"))
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0]["mensaje"], "sesion abierta")


if __name__ == "__main__":
    unittest.main()
