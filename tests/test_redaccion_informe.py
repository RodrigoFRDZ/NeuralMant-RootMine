import copy
import unittest
from io import BytesIO
from pypdf import PdfReader
from motores.redaccion_informe import consolidar,corregir
from motores.foco_partida import focos
from reportes.trabajos import render_pdf


def ejemplo():
    observacion='quedo un poco de huelo en algunos rieles, y partes superiores de la camara'
    return dict(id=1,descripcion='MP 1S 2P RETIRO HIELO CARTON FREZER',area='ADM-DESP',estado='Terminado',avance=100,prueba='Aprobada',pendiente='',
        hallazgos='Observación en pruebas: '+observacion+' | La observación no impide la partida ni el funcionamiento normal.',
        detalle_prueba='Observación durante la prueba: '+observacion+' · El supervisor informa que no impide la partida ni el funcionamiento normal.',
        ultimo_mensaje='Trabajo se atrasa por personal contratista, se logra terminar a tiempo independiente de la hora de ingreso',
        historial=[dict(mensaje='Trabajo se atrasa por personal contratista, se logra terminar a tiempo independiente de la hora de ingreso')],fotos=[])


class RedaccionInformeTest(unittest.TestCase):
    def test_captura_se_consolida_sin_retraso_mezclado_y_sin_editar_bitacora(self):
        d=ejemplo();antes=copy.deepcopy(d);f=focos([d])
        texto=f['semana'][0]['detalle']
        self.assertEqual(texto.lower().count('hielo'),1)
        self.assertEqual(texto.count('no impide'),1)
        self.assertIn('Quedó',texto);self.assertIn('cámara',texto)
        self.assertIn('rieles',texto);self.assertIn('partes superiores',texto)
        self.assertNotIn('contratista',texto)
        self.assertIn('contratista',f['retrasos'][0]['detalle'])
        self.assertEqual(d,antes)

    def test_palabra_ambigua_no_se_sustituye_sin_contexto(self):
        self.assertEqual(corregir('huelo algo extraño','Cambio de motor'),'huelo algo extraño')
        self.assertEqual(corregir('Queda huelo','Retiro de hielo'),'Queda hielo')

    def test_no_omite_negacion_ni_otro_hallazgo_o_ubicacion(self):
        texto=consolidar(['Fuga en sello. No hay fuga en tubería.','Fuga en sello. Vibración en motor.'])
        self.assertEqual(texto.count('Fuga en sello'),1)
        self.assertIn('No hay fuga en tubería',texto)
        self.assertIn('Vibración en motor',texto)

    def test_ia_recibe_focos_y_pide_correccion_contextual(self):
        import json
        from unittest.mock import patch
        from ia.resumen_turno import mejorar_resumen,ResumenTurno,FocoRedactado
        respuesta=ResumenTurno(comentario='Prueba aprobada con hielo remanente en seguimiento.',sugerencias='Revisar el hielo remanente.',focos=[FocoRedactado(id='semana:0',detalle='Hielo remanente en rieles; sin impedimento informado para la partida.',accion='Revisar el hielo remanente.')])
        with patch('ia.resumen_turno._generar',return_value=respuesta) as generar:
            resultado=mejorar_resumen([ejemplo()],dict(comentario='',sugerencias=''))
        sistema,contenido,_=generar.call_args.args
        self.assertIn('ortografía',sistema)
        self.assertIn('Si una palabra es ambigua',sistema)
        fuentes=json.loads(contenido)['registros']
        self.assertTrue(any(r.get('id')=='semana:0' and r['tipo']=='foco_para_redactar' for r in fuentes))
        self.assertEqual(resultado['focos'][0]['id'],'semana:0')

    def test_pdf_usa_redaccion_ia_solo_en_foco_indicado(self):
        corte=dict(titulo='Revisión de redacción',centro='1802',fecha='2026-10-18',turno='Día',generado='2026-10-18T12:00:00',nombre='Supervisor',trabajos=[ejemplo()],novedades_area=[],
            focos_redactados=[dict(id='semana:0',detalle='Persiste hielo en rieles y parte superior de la cámara; según el supervisor, no impide la partida ni el funcionamiento normal.',accion='Propuesta: revisar el hielo remanente.')])
        pdf=render_pdf(corte)
        texto=' '.join(' '.join(p.extract_text().split()) for p in PdfReader(BytesIO(pdf)).pages)
        self.assertIn('Persiste hielo en rieles',texto)
        self.assertIn('revisar el hielo remanente',texto)
        self.assertIn('contratista',texto)
        self.assertNotIn('huelo',texto)
        from pathlib import Path
        Path('/tmp/neuralmant_redaccion_4817.pdf').write_bytes(pdf)
