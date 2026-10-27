import unittest
from unittest.mock import patch
from ia.etapas_trabajos import ACEITE, validar_plan, calcular, porcentaje_escrito
from ia.avance_trabajos import preparar_propuesta

class EtapasTest(unittest.TestCase):
    def test_aceite_acumula_sin_inferir_pasos_anteriores(self):
        self.assertEqual(calcular(ACEITE,[],[3],[]),(35,[3]))
        self.assertEqual(calcular(ACEITE,[1,2],[3],[]),(75,[1,2,3]))
        self.assertEqual(calcular(ACEITE,[1,2,3],[],[3]),(40,[1,2]))
        with self.assertRaises(ValueError):calcular(ACEITE,[],[6],[])
    def test_porcentaje_textual_tiene_prioridad_sobre_etapas(self):
        d=dict(descripcion='Cambio de aceite',etapas_confirmadas=[1,2])
        with patch('ia.avance_trabajos.proponer',return_value=dict(etapas_completadas=[3],estado='Terminado')):
            propuesta=preparar_propuesta(d,'Aceite cargado. Vamos al 80%.')
        self.assertEqual(propuesta['avance'],80)
        self.assertEqual(propuesta['estado'],'En ejecución')
        self.assertEqual(propuesta['origen_avance'],'informado_supervisor')
        self.assertEqual(porcentaje_escrito('Faltan 20 litros'),None)
    def test_estimacion_etapas_no_aprueba_prueba(self):
        d=dict(descripcion='MP 6M LUB CAMBIO ACEITE CHILLER L2',etapas_confirmadas=[1,2])
        with patch('ia.avance_trabajos.proponer',return_value=dict(etapas_completadas=[3])):
            propuesta=preparar_propuesta(d,'Aceite nuevo cargado.')
        self.assertEqual(propuesta['avance'],75)
        self.assertEqual(propuesta['origen_avance'],'estimado_etapas')
        self.assertNotIn('prueba',propuesta)
        self.assertEqual(propuesta['etapas_confirmadas'],[1,2,3])
    def test_trabajo_nuevo_propone_plan_sin_imponer_porcentaje(self):
        plan=[dict(etapa='Cambio',peso=60),dict(etapa='Prueba',peso=40)]
        with patch('ia.etapas_trabajos.proponer_plan',return_value=plan),patch('ia.avance_trabajos.proponer',return_value={}):
            propuesta=preparar_propuesta(dict(descripcion='Cambio de sensor'),'Tenemos los materiales')
        self.assertTrue(propuesta['plan_nuevo'])
        self.assertNotIn('avance',propuesta)
        with self.assertRaises(ValueError):validar_plan([dict(etapa='Cambio',peso=10),dict(etapa='Prueba',peso=30)])
