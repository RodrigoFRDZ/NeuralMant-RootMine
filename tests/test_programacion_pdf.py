import unittest
from unittest.mock import patch
from modulos.programacion_pdf import extraer_trabajos, ProgramacionExtraida, TrabajoExtraido

TABLA='''PÁGINA 1
Supervisor: Esteban Nilo
FAENA
 16120892  11-oct.-26  11-oct.-26  SYR    MP 6M LUB CAMBIO ACEITE CHILLER L1    X
 16148227  11-oct.-26  25-oct.-26  PINTORES    INFR PINTURA PANELES CIELO    X    X
EMPRESAS CONTRATISTAS EN AREA - FAENA
SYR PINTORES
PÁGINA 2
ADM - DESPACHO
 16146999  11-oct.-26  11-oct.-26  C JIMENE    MJ INST PARADAS PIOLA EMERG PDZ 1 Y PDZ2    X
'''
class ImportacionPDFTest(unittest.TestCase):
    def test_tabla_sin_ia_preserva_fechas_ejecutor_y_area(self):
        with patch('modulos.programacion_pdf._generar',side_effect=AssertionError('No necesita IA')):
            filas=extraer_trabajos(TABLA)
        self.assertEqual(len(filas),3)
        self.assertEqual(filas[0]['linea'],'L1')
        self.assertEqual(filas[1]['fin_plan'],'25-oct.-26')
        self.assertEqual(filas[2]['ejecutor'],'C JIMENE')
        self.assertEqual(filas[2]['area'],'ADM-DESP')
        self.assertEqual(filas[2]['referencia_pdf'],'Página 2 · OT 16146999')
        self.assertTrue(all('supervisor' not in f for f in filas))
        self.assertTrue(all(not f['descripcion'].endswith(' X') for f in filas))
    def test_tabla_incompleta_no_se_publica_parcialmente(self):
        with self.assertRaisesRegex(ValueError,'tabla incompleta'):
            extraer_trabajos(TABLA+' 16126048  11-oct.-26  11-oct.-26  MALFORMADA\n')
    def test_respuesta_truncada_descarta_todos_los_bloques(self):
        texto='PÁGINA 1\n'+'Trabajo descrito de manera libre\n'*150
        primero=ProgramacionExtraida(trabajos=[TrabajoExtraido(descripcion='Trabajo')])
        with patch('modulos.programacion_pdf._generar',side_effect=[primero,ValueError('EOF')]) as generar:
            with self.assertRaisesRegex(ValueError,'No se importaron filas parciales'):
                extraer_trabajos(texto)
        self.assertEqual(generar.call_count,2)
        self.assertTrue(all(len(c.args[1])<=2515 for c in generar.call_args_list))
    def test_ot_no_se_recorta_con_volumen(self):
        texto='PÁGINA 1\nSERVICIOS\n'+''.join(f'{15000000+i}  10-oct.-26  12-oct.-26  TECNICO    Trabajo {i}    X\n' for i in range(96))
        with patch('modulos.programacion_pdf._generar',side_effect=AssertionError()):filas=extraer_trabajos(texto)
        self.assertEqual(len(filas),96)
        self.assertEqual(len({f['ot'] for f in filas}),96)
