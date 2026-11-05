import unittest
from unittest.mock import patch
from ia.novedad_automatica import interpretar,combinar,NovedadAutomatica

D=dict(descripcion='Cambio de aceite',estado='Pendiente',avance=0,prueba='Pendiente',pendiente='',hallazgos='',detalle_prueba='')
class AutomaticoTest(unittest.TestCase):
    def test_porcentaje_directo_sin_llamar_ia(self):
        with patch('ia.novedad_automatica._generar',side_effect=AssertionError('No debe esperar a IA')):
            nuevo=combinar(D,interpretar(D,'avance 60%'))
        self.assertEqual(nuevo['avance'],60);self.assertEqual(nuevo['estado'],'En ejecución')
        self.assertEqual(nuevo['prueba'],'Pendiente')
    def test_falta_informacion_pregunta_y_no_aplica(self):
        with patch('ia.novedad_automatica._generar',return_value=NovedadAutomatica(pregunta='¿Terminó el montaje o toda la pega?')):
            self.assertEqual(interpretar(D,'quedó listo'),{'pregunta':'¿Terminó el montaje o toda la pega?'})
    def test_una_sola_llamada_para_estimar_etapas(self):
        with patch('ia.novedad_automatica._generar',return_value=NovedadAutomatica(etapas_completadas=[1,2],estado='En ejecución')) as llamada:
            nuevo=combinar(D,interpretar(D,'Preparación y drenaje terminados'))
        self.assertEqual(llamada.call_count,1)
        self.assertEqual(nuevo['avance'],40)
        self.assertEqual(nuevo['prueba'],'Pendiente')
    def test_prueba_sin_evidencia_pide_dato(self):
        self.assertIn('pregunta',combinar(D,{'prueba':'Aprobada'}))
    def test_porcentaje_no_elimina_bloqueo(self):
        bloqueado=D|dict(estado='Detenido',avance=20,pendiente='Falta repuesto')
        self.assertEqual(combinar(bloqueado,interpretar(bloqueado,'50%'))['estado'],'Detenido')
