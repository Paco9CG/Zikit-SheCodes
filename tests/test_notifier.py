import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.notifier import enviar_sms_infobip, notificar_incidencia_real, _normalizar_numero, ACCIONES_SUGERIDAS


class NotifierTests(unittest.TestCase):
    def test_normalizar_numero(self):
        self.assertEqual(_normalizar_numero("8713280948"), "528713280948")
        self.assertEqual(_normalizar_numero("+528713280948"), "528713280948")
        self.assertEqual(_normalizar_numero("528713280948"), "528713280948")
        self.assertEqual(_normalizar_numero(""), "")

    def test_acciones_sugeridas_mapeo(self):
        self.assertIn("deriva_disco", ACCIONES_SUGERIDAS)
        self.assertIn("fuga_memoria_worker", ACCIONES_SUGERIDAS)
        self.assertIn("saturacion_bd_gradual", ACCIONES_SUGERIDAS)
        self.assertIn("crecimiento_cache_gps", ACCIONES_SUGERIDAS)

    @patch("http.client.HTTPSConnection")
    def test_enviar_sms_infobip_exito(self, mock_conn_cls):
        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'{"messages": [{"messageId": "msg_v3_test_123", "status": {"groupName": "PENDING"}}]}'
        mock_conn.getresponse.return_value = mock_response
        mock_conn_cls.return_value = mock_conn

        resultado = enviar_sms_infobip(
            texto="Alerta Test",
            base_url="https://rkxxql.api.infobip.com",
            api_key="App secret_key",
            sender="8711668582",
            to_num="528713280948"
        )
        self.assertEqual(resultado, "msg_v3_test_123")

    @patch("http.client.HTTPSConnection")
    def test_notificar_incidencia_real_incluye_accion(self, mock_conn_cls):
        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'{"messages": [{"messageId": "msg_incidencia_v3"}]}'
        mock_conn.getresponse.return_value = mock_response
        mock_conn_cls.return_value = mock_conn

        sid = notificar_incidencia_real("gracko", "deriva_disco", 0.94, "2026-10-10T08:00:00")
        self.assertEqual(sid, "msg_incidencia_v3")


if __name__ == "__main__":
    unittest.main()
