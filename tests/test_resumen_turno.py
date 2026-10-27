import unittest
from unittest.mock import patch
from ia.resumen_turno import resumen_base,mejorar_resumen,ResumenTurno

class ResumenTest(unittest.TestCase):
    def test_chat_informado_no_cambia_estado_y_guarda_atribucion(self):
        filas=[dict(id=1,ot='12345678',area='Faena',descripcion='Rodamiento',estado='En ejecución',avance=50,prueba='Pendiente',pendiente='Falta prueba',hallazgos='',historial=[dict(nombre='Supervisor Uno',usuario='uno@test',fecha='2026-10-13T19:00:00',mensaje='Montaje terminado; falta probar')])]
        resumen=resumen_base(filas)
        self.assertNotIn('Supervisor Uno',resumen['comentario'])
        self.assertNotIn('Montaje terminado; falta probar',resumen['comentario'])
        self.assertIn('Rodamiento · Faena',resumen['comentario'])
        self.assertIn('confirmar pruebas',resumen['sugerencias'])
        with patch('ia.resumen_turno._generar',return_value=ResumenTurno(comentario='Montaje informado; prueba pendiente.',sugerencias='Propuesta: coordinar prueba.')):
            mejorado=mejorar_resumen(filas,resumen)
        self.assertIn('prueba pendiente',mejorado['comentario'])
        self.assertEqual(filas[0]['estado'],'En ejecución')
        self.assertEqual(filas[0]['avance'],50)

    def test_bitacora_extensa_se_divide_y_conserva_ultima_observacion(self):
        import json,copy
        from ia.resumen_turno import SintesisParcial
        d=dict(id=1,area='Faena',descripcion='Transportador',estado='Terminado',avance=100,prueba='Pendiente',pendiente='Validar funcionamiento',hallazgos='',detalle_prueba='',fotos=['IMAGEN_NO_ENVIAR'*10000],historial=[])
        for i in range(180):d['historial'].append(dict(fecha=str(i),nombre='Supervisor',mensaje=f'OBSERVACION_{i:03d} '+('Detalle técnico del montaje. '*80)))
        d['historial'][-1]['mensaje']+=' HALLAZGO_CRITICO_AL_FINAL'
        original=copy.deepcopy(d);llamadas=[]
        def generar(sistema,contenido,esquema):
            llamadas.append((json.loads(contenido),contenido,esquema))
            return SintesisParcial(comentario='Transportador: validación pendiente.',sugerencias='Propuesta: verificar.') if esquema is SintesisParcial else ResumenTurno(comentario='Conclusión consolidada.',sugerencias='Validar funcionamiento.')
        with patch('ia.resumen_turno._generar',side_effect=generar):resultado=mejorar_resumen([d],dict(comentario='',sugerencias=''))
        self.assertGreater(len(llamadas),2)
        contenido=' '.join(c for _,c,_ in llamadas)
        self.assertNotIn('IMAGEN_NO_ENVIAR',contenido)
        self.assertIn('HALLAZGO_CRITICO_AL_FINAL',contenido)
        for i in range(180):self.assertIn(f'OBSERVACION_{i:03d}',contenido)
        self.assertTrue(all(len(c)<60000 for _,c,_ in llamadas))
        self.assertEqual(llamadas[-1][0]['indicadores_globales']['actividades'],1)
        self.assertEqual(resultado['comentario'],'Conclusión consolidada.');self.assertEqual(d,original)

    def test_campo_muy_extenso_se_fragmenta_sin_perder_texto(self):
        import json
        from ia.resumen_turno import _fragmentos,PRESUPUESTO_LOTE
        texto='Primera observación. '+('x'*110000)+' Última observación de seguridad.'
        registro=dict(tipo='novedad_area',id=1,area='Faena',mensaje=texto,estado='Abierto')
        partes=list(_fragmentos(registro))
        reconstruido=json.loads(''.join(p['fragmento'] for p in partes if p['campo']=='mensaje'))
        self.assertEqual(reconstruido,texto)
        self.assertTrue(all(len(json.dumps(p,ensure_ascii=False))<PRESUPUESTO_LOTE for p in partes))

    def test_consolidacion_en_varios_niveles(self):
        import json
        from ia.resumen_turno import SintesisParcial
        d=dict(id=1,area='Faena',descripcion='Motor',estado='Terminado',avance=100,prueba='Aprobada',detalle_prueba='Normal',pendiente='',hallazgos='',historial=[dict(fecha=str(i),mensaje=str(i)+'x'*4000,nombre='Supervisor') for i in range(35)])
        niveles=[]
        def generar(sistema,contenido,esquema):
            contexto=json.loads(contenido);niveles.append(contexto.get('nivel',-1))
            self.assertLess(len(contenido),13000)
            if esquema is SintesisParcial:return SintesisParcial(comentario='Resumen de antecedentes. '+('x'*3500),sugerencias='Propuesta de revisión.')
            return ResumenTurno(comentario='Resultado final.',sugerencias='Seguimiento.')
        with patch('ia.resumen_turno.PRESUPUESTO_LOTE',12000),patch('ia.resumen_turno._generar',side_effect=generar):
            resultado=mejorar_resumen([d],dict(comentario='',sugerencias=''))
        self.assertIn(1,niveles);self.assertEqual(niveles[-1],-1);self.assertEqual(resultado['comentario'],'Resultado final.')
