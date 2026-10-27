import unittest
from io import BytesIO
from pypdf import PdfReader
from reportes.trabajos import render_pdf

class FormatoReporteTest(unittest.TestCase):
    def test_titulos_acompanan_contenido_en_informes_de_varias_paginas(self):
        base=dict(estado='Terminado',avance=100,prueba='Pendiente',pendiente='Falta verificar la marcha del equipo.',hallazgos='',historial=[],detalle_prueba='',fotos=[])
        filas=[dict(base,id=i+1,area='Faena',descripcion=f'Actividad {i+1}: revisión de rodamientos del transportador de salida') for i in range(24)]
        titulos=['01 / Conclusión ejecutiva','02 / Estado de entrega por área','Actividades del programa','03 / Prioridades y acciones propuestas','04 / Novedades de las áreas','05 / Evidencia fotográfica']
        for repeticiones in [1,12]:
            corte=dict(titulo='Informe de formato',centro='1802',fecha='2026-10-18',turno='Día',generado='2026-10-18T12:00:00',nombre='Supervisor',trabajos=filas,novedades_area=[],comentario='Confirmar las pruebas pendientes y documentar las condiciones de entrega antes de la partida. '*repeticiones)
            paginas=PdfReader(BytesIO(render_pdf(corte))).pages
            self.assertGreater(len(paginas),1)
            encontrados=set()
            for pagina in paginas:
                lineas=[l.strip() for l in pagina.extract_text().splitlines() if l.strip() and not l.startswith(('NeuralMant ·','Página '))]
                for i,linea in enumerate(lineas):
                    if linea in titulos:
                        encontrados.add(linea)
                        self.assertLess(i,len(lineas)-1,'Título sin contenido en la misma página: '+linea)
            self.assertEqual(encontrados,set(titulos))

    def test_resultados_y_observaciones_largos_se_imprimen_completos(self):
        prueba='Observación durante la prueba: rodamiento nuevo no contaba con puntos de lubricación. '+('Se debe coordinar el cambio por los rodamientos que corresponden. '*12)+' FIN DE LA PRUEBA COMPLETA'
        hallazgo=('Vibración en seguimiento semanal: verificar lubricación y condición del equipo. '*14)+' FIN DEL HALLAZGO COMPLETO'
        fila=dict(id=1,area='Congelado',descripcion='MP 1A CC TENSOR BOLSA MD PACMAC 3',estado='Terminado',avance=100,prueba='Aprobada',detalle_prueba=prueba,pendiente='',hallazgos=hallazgo,historial=[],fotos=[])
        novedad=dict(id=1,area='Congelado',categoria='Calidad',estado='Resuelto',mensaje=('Antecedente de calidad para revisión. '*15)+' FIN DE LA NOVEDAD COMPLETA',nombre='Supervisor',fecha='2026-10-18T12:00:00',cierre=dict(nombre='Supervisor',mensaje=('Se verificó la corrección en terreno. '*15)+' FIN DE LA RESOLUCION COMPLETA'))
        corte=dict(titulo='Texto completo',centro='1802',fecha='2026-10-18',turno='Día',generado='2026-10-18T12:00:00',nombre='Supervisor',trabajos=[fila],novedades_area=[novedad])
        lector=PdfReader(BytesIO(render_pdf(corte)))
        texto=' '.join(' '.join(p.extract_text().split()) for p in lector.pages)
        for final in ['FIN DE LA PRUEBA COMPLETA','FIN DEL HALLAZGO COMPLETO','FIN DE LA NOVEDAD COMPLETA','FIN DE LA RESOLUCION COMPLETA']:self.assertIn(final,texto)
        self.assertNotIn('…',texto)

    def test_fila_y_leyenda_mayores_a_una_pagina_no_se_cortan(self):
        import base64
        from PIL import Image
        salida=BytesIO();Image.new('RGB',(50,30),'orange').save(salida,format='PNG')
        mensaje=('Hallazgo que debe revisarse y verificarse en terreno antes de la partida. '*140)+' FIN DE LEYENDA EXTENSA'
        novedad=dict(id=1,area='Faena',categoria='Calidad',estado='Abierto',mensaje=mensaje,nombre='Supervisor',fecha='2026-10-18T12:00:00',fotos=[dict(nombre='Prueba',contenido=base64.b64encode(salida.getvalue()).decode())])
        corte=dict(titulo='Texto extenso',centro='1802',fecha='2026-10-18',turno='Día',generado='2026-10-18T12:00:00',nombre='Supervisor',trabajos=[],novedades_area=[novedad])
        lector=PdfReader(BytesIO(render_pdf(corte)))
        texto=' '.join(' '.join(p.extract_text().split()) for p in lector.pages)
        self.assertGreater(len(lector.pages),2)
        self.assertGreaterEqual(texto.count('FIN DE LEYENDA EXTENSA'),2)
        self.assertTrue(any(len(p.images)>0 for p in lector.pages))
