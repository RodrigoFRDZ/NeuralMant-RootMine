import unittest
from unittest.mock import patch
from pydantic import BaseModel,Field,ValidationError
from ia.cliente import ConfiguracionIA
from ia.diagnostico import diagnosticar_resumen

class DiagnosticoIATest(unittest.TestCase):
    def test_oculta_clave_en_pantalla_y_logs(self):
        clave='AIza'+'X'*35
        with patch('ia.diagnostico.obtener_configuracion',return_value=ConfiguracionIA('Gemini',clave,'modelo-prueba')):
            with self.assertLogs('neuralmant.ia.resumen',level='ERROR') as registro:
                d=diagnosticar_resumen(RuntimeError('auth api_key='+clave+' Bearer token-secreto token=visible'))
        self.assertNotIn(clave,d['detalle']);self.assertNotIn('token-secreto',d['detalle'])
        self.assertNotIn(clave,' '.join(registro.output));self.assertNotIn('token-secreto',' '.join(registro.output))
        self.assertIn(d['referencia'],' '.join(registro.output))

    def test_validacion_no_expone_contenido_de_entrada(self):
        class Respuesta(BaseModel):comentario:str=Field(max_length=2)
        try:Respuesta(comentario='REGISTRO_PRIVADO_QUE_NO_DEBE_IR_AL_LOG')
        except ValidationError as error:
            with patch('ia.diagnostico.obtener_configuracion',return_value=ConfiguracionIA('Gemini','','modelo-prueba')):
                with self.assertLogs('neuralmant.ia.resumen',level='ERROR') as registro:d=diagnosticar_resumen(error)
        self.assertNotIn('REGISTRO_PRIVADO',d['detalle']);self.assertNotIn('REGISTRO_PRIVADO',' '.join(registro.output))
        self.assertIn('formato requerido',d['mensaje'])
