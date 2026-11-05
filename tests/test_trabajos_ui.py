import unittest
from streamlit.testing.v1 import AppTest

SCRIPT="""
import streamlit as st
from modulos import trabajos as m
m.area_db.listar=lambda *a:[]
st.session_state.setdefault('usuario_actual',dict(correo='sup@test.cl',nombre='Supervisor',rol='supervisor',centro='1802',es_admin=False))
m.db.programas=lambda correo:[dict(id=1,titulo='Fin de semana',centro='1802',inicio='2026-10-17',fin='2026-10-18',fuente='plan.pdf')]
m.db.fuente=lambda *a:b'%PDF-1.4'
m.db.evidencia=lambda *a:[]
d=dict(id=1,version=1,descripcion='Rodamiento',linea='L1',area='Faena',equipo='Transportador',supervisor='sup@test.cl',referencia_pdf='',estado='Pendiente',avance=0,pendiente='',hallazgos='',prueba='Pendiente',detalle_prueba='',actualizado='',autor='',fotos=[],historial=[])
st.session_state.setdefault('_trabajo_test',d)
m.db.trabajos=lambda *a:[st.session_state['_trabajo_test']]
def actualizar(*args,**kwargs):
    st.session_state['_guardado']=args[4]
    actual=dict(st.session_state['_trabajo_test']);actual.update(args[4]);actual['version']+=1
    if kwargs.get('mensaje'):
        actual['ultimo_mensaje']=kwargs['mensaje']
        actual['historial']=actual['historial']+[dict(nombre='Supervisor',fecha='2026-10-13T18:00:00',mensaje=kwargs['mensaje'],**{k:actual[k] for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba')})]
    st.session_state['_trabajo_test']=actual
    return actual['version']
m.db.actualizar=actualizar
from motores.pruebas_trabajos import transicion
def registrar_prueba(correo,n,ident,version,accion,texto=''):
    return actualizar(correo,n,ident,version,transicion(st.session_state['_trabajo_test'],accion,texto),mensaje=texto or accion)
m.db.registrar_prueba=registrar_prueba
m.db.ultima_novedad=lambda *a:None
m.db.descartar_novedades_anteriores=lambda *a:None
m.db.encolar_novedad=lambda *a:1
from ia import cola_novedades
cola_novedades.iniciar=lambda:None
m.mostrar_trabajos()
"""
class TrabajosUITest(unittest.TestCase):
    def test_botones_prueba_y_terminado_reciben_foto_seleccionada(self):
        upload_script="""
from io import BytesIO
from unittest.mock import patch
f=BytesIO(b'foto-seleccionada');f.name='evidencia.png';f.size=len(f.getvalue())
original_actualizar=m.db.actualizar
original_registrar=m.db.registrar_prueba
def guardar_con_fotos(*args,**kwargs):
    st.session_state['_fotos_recibidas']=args[5] if len(args)>5 else kwargs.get('fotos',[])
    return original_actualizar(*args,**kwargs)
def prueba_con_fotos(*args,**kwargs):
    fotos=kwargs.pop('fotos',[])
    resultado=original_registrar(*args,**kwargs)
    st.session_state['_fotos_recibidas']=fotos
    return resultado
m.db.actualizar=guardar_con_fotos
m.db.registrar_prueba=prueba_con_fotos
with patch.object(m.st,'file_uploader',return_value=[f]):
    m.mostrar_trabajos()
"""
        for estado,paso,etiqueta in [('Pendiente',None,'Trabajo terminado'),('Terminado','realizacion','Sí, se realizaron'),('Terminado','realizacion','Aún no'),('Terminado','observaciones','Funcionamiento normal, sin observaciones')]:
            with self.subTest(etiqueta=etiqueta):
                script=SCRIPT.replace('m.mostrar_trabajos()',upload_script)
                at=AppTest.from_string(script).run(timeout=15)
                d=dict(at.session_state['_trabajo_test'])
                d.update(estado=estado,avance=100 if estado=='Terminado' else 0,prueba='En prueba' if paso=='observaciones' else 'Pendiente',dialogo_prueba={'paso':paso})
                at.session_state['_trabajo_test']=d
                at.session_state['trab_chat_area_1']='Faena'
                at.session_state['trab_chat_activo_1']=1
                at.session_state['trab_chat_incluir_terminados_1']=True
                at.radio(key='trab_vista').set_value('Chat de avance').run()
                next(b for b in at.button if b.label==etiqueta).click().run()
                self.assertEqual(len(at.exception),0,str(at.exception))
                self.assertEqual(at.session_state['_fotos_recibidas'],[('evidencia.png',b'foto-seleccionada')])
                self.assertTrue(any('1 foto(s) guardadas correctamente' in x.value for x in at.success))

    def test_tablero_y_supervisor_guarda_sin_perder_por_refresco(self):
        at=AppTest.from_string(SCRIPT).run(timeout=15)
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertNotIn('Cargar programación',at.radio(key='trab_vista').options)
        self.assertEqual(len(at.metric),4)
        at.session_state['trab_chat_activo_1']=1
        at.radio(key='trab_vista').set_value('Chat de avance').run()
        at.toggle(key='trab_chat_detalle_1_1').set_value(True).run()
        at.selectbox(key='trab_form_1_estado').set_value('En ejecución')
        at.number_input(key='trab_form_1_avance').set_value(50)
        at.text_area(key='trab_form_1_pendiente').set_value('Falta montaje')
        next(b for b in at.button if b.label=='Guardar avance').click().run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertEqual(at.session_state['_guardado']['avance'],50)
        self.assertIn('Avance guardado',' '.join(x.value for x in at.success))

    def test_partida_por_area_no_confunde_terminado_con_probado(self):
        from modulos.trabajos import preparacion_por_area
        base=dict(area='Faena',estado='Terminado',prueba='Aprobada',pendiente='',detalle_prueba='OK')
        filas=[base,dict(base,prueba='Pendiente'),dict(base,pendiente='Falta ajustar'),dict(base,estado='En ejecución'),dict(base,prueba='No requerida',detalle_prueba='No aplica según pauta'),dict(base,prueba='No requerida',detalle_prueba=''),dict(base,area='Procesos')]
        self.assertEqual(preparacion_por_area(filas),[dict(area='Faena',total=6,probados=1,sin_prueba=1),dict(area='Procesos',total=1,probados=1,sin_prueba=0)])

    def test_roles_solo_consultan_o_publican_sin_chat(self):
        for rol in ['tecnico','jefe','ingeniero','subgerente','programador_mantenimiento']:
            script=SCRIPT.replace("rol='supervisor'", "rol="+repr(rol))
            at=AppTest.from_string(script).run(timeout=15)
            self.assertEqual(len(at.exception),0,str(at.exception))
            self.assertNotIn('Chat de avance',at.radio(key='trab_vista').options)
            self.assertEqual('Cargar programación' in at.radio(key='trab_vista').options,rol=='programador_mantenimiento')
            self.assertEqual(len(at.get('vega_lite_chart')),0)
            self.assertTrue(any('probados y listos' in x.label for x in at.button))
        at=AppTest.from_string(SCRIPT.replace('es_admin=False','es_admin=True')).run(timeout=15)
        self.assertIn('Chat de avance',at.radio(key='trab_vista').options)
        self.assertIn('Cargar programación',at.radio(key='trab_vista').options)

    def test_porcentaje_se_actualiza_sin_confirmacion_y_relato_se_encola(self):
        at=AppTest.from_string(SCRIPT).run(timeout=15)
        at.radio(key='trab_vista').set_value('Chat de avance').run()
        at.selectbox(key='trab_chat_area_1').set_value('Faena').run()
        at.selectbox(key='trab_chat_activo_1').set_value(1).run()
        at.chat_input[0].set_value('avance 60%').run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertEqual(at.session_state['_trabajo_test']['avance'],60)
        self.assertEqual(at.session_state['_trabajo_test']['estado'],'En ejecución')
        self.assertNotIn('Confirmar actualización',[x.label for x in at.button])
        at.chat_input[0].set_value('Montaje realizado; falta alinear').run()
        self.assertEqual(at.session_state['_trabajo_test']['ultimo_mensaje'],'Montaje realizado; falta alinear')
        self.assertTrue(any('puedes seguir' in x.value for x in at.success))

    def test_coordinador_y_supervisor_ven_chat_de_ot_asignada_a_otro(self):
        for rol in ['supervisor','coordinador_mantenimiento']:
            script=SCRIPT.replace("rol='supervisor'", "rol="+repr(rol)).replace("supervisor='sup@test.cl'", "supervisor='otro@test.cl'")
            at=AppTest.from_string(script).run(timeout=15)
            self.assertEqual(len(at.exception),0,str(at.exception))
            self.assertIn('Chat de avance',at.radio(key='trab_vista').options)
            at.radio(key='trab_vista').set_value('Chat de avance').run()
            self.assertEqual(len(at.exception),0,str(at.exception))
            at.selectbox(key='trab_chat_area_1').set_value('Faena').run()
            self.assertTrue(any('Rodamiento' in op for op in at.selectbox(key='trab_chat_activo_1').options))
            at.selectbox(key='trab_chat_activo_1').set_value(1).run()
            self.assertEqual(len(at.chat_input),1)

    def test_reporte_resumen_editable_y_una_descarga_sin_generar_o_cerrar(self):
        script=SCRIPT.replace('m.mostrar_trabajos()',"m.generar_pdf=lambda *a:b'%PDF-test'\nm.mostrar_trabajos()")
        at=AppTest.from_string(script).run(timeout=15)
        at.radio(key='trab_vista').set_value('Reportes de turno').run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertIn('Faena',at.text_area(key='trab_resumen_1_comentario').value)
        at.text_area(key='trab_resumen_1_comentario').set_value('Resumen revisado por supervisor').run()
        self.assertEqual(at.text_area(key='trab_resumen_1_comentario').value,'Resumen revisado por supervisor')
        self.assertEqual(len(at.get('download_button')),1)
        self.assertNotIn('Registrar cierre de turno',[x.label for x in at.button])
        self.assertNotIn('Generar informe',[x.label for x in at.button])

    def test_historico_solo_muestra_pdf_y_no_chat(self):
        script=SCRIPT.replace("fuente='plan.pdf'","fuente='plan.pdf',cerrado=True,vence='2027-01-13T00:00:00'").replace('m.mostrar_trabajos()',"m.db.historico_pdf=lambda *a:b'%PDF-test'\nm.mostrar_trabajos()")
        at=AppTest.from_string(script).run(timeout=15)
        at.radio(key='trab_vista').set_value('Chat de avance').run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertEqual(len(at.chat_input),0)
        self.assertEqual(len(at.text_area),0)
        self.assertTrue(any('Programa cerrado' in x.value for x in at.info))

    def test_fallo_de_ia_conserva_resumen_manual_y_descarga(self):
        script=SCRIPT.replace('m.mostrar_trabajos()',"from ia import resumen_turno\ndef fallar(*args):raise RuntimeError('503')\nresumen_turno.mejorar_resumen=fallar\nm.generar_pdf=lambda *a:b'%PDF-test'\nm.mostrar_trabajos()")
        at=AppTest.from_string(script).run(timeout=15)
        at.radio(key='trab_vista').set_value('Reportes de turno').run()
        at.text_area(key='trab_resumen_1_comentario').set_value('Resumen escrito por supervisor').run()
        next(x for x in at.button if x.label=='Analizar y sintetizar con GearBot').click().run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertEqual(at.text_area(key='trab_resumen_1_comentario').value,'Resumen escrito por supervisor')
        self.assertEqual(len(at.get('download_button')),1)
        self.assertTrue(any('se conserva' in x.value for x in at.warning))

    def test_cambiar_area_limpia_pega_y_filtra_pendientes(self):
        extra="""
from ia import avance_trabajos
avance_trabajos.preparar_propuesta=lambda *a:{}
m.db.trabajos=lambda *a:[st.session_state['_trabajo_test'],dict(st.session_state['_trabajo_test'],id=2,area='Procesos',descripcion='Cambio de aceite'),dict(st.session_state['_trabajo_test'],id=3,area='Faena',descripcion='Trabajo resuelto',estado='Terminado',avance=100,prueba='Aprobada',pendiente='')]
original=m.db.actualizar
def registrar(*args,**kwargs):
    st.session_state['_id_guardado']=args[2]
    return original(*args,**kwargs)
m.db.actualizar=registrar
m.mostrar_trabajos()
"""
        at=AppTest.from_string(SCRIPT.replace('m.mostrar_trabajos()',extra)).run(timeout=15)
        at.radio(key='trab_vista').set_value('Chat de avance').run()
        self.assertEqual(len(at.chat_input),0)
        at.selectbox(key='trab_chat_area_1').set_value('Faena').run()
        selector=at.selectbox(key='trab_chat_activo_1')
        self.assertFalse(any('Trabajo resuelto' in op for op in selector.options))
        at.selectbox(key='trab_chat_activo_1').set_value(1).run()
        at.selectbox(key='trab_chat_area_1').set_value('Procesos').run()
        self.assertEqual(at.selectbox(key='trab_chat_activo_1').value,0)
        self.assertFalse(any('Rodamiento' in op for op in at.selectbox(key='trab_chat_activo_1').options))
        at.selectbox(key='trab_chat_activo_1').set_value(2).run()
        at.chat_input[0].set_value('Drenaje realizado').run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertEqual(at.session_state['_id_guardado'],2)
        self.assertEqual(at.selectbox(key='trab_chat_area_1').value,'Procesos')

    def test_novedad_fallida_no_se_reasigna_al_cambiar_area(self):
        extra="""
m.db.trabajos=lambda *a:[st.session_state['_trabajo_test'],dict(st.session_state['_trabajo_test'],id=2,area='Procesos')]
def fallar(*args,**kwargs):raise ValueError('Otro usuario actualizó el trabajo')
m.db.actualizar=fallar
m.mostrar_trabajos()
"""
        at=AppTest.from_string(SCRIPT.replace('m.mostrar_trabajos()',extra)).run(timeout=15)
        at.radio(key='trab_vista').set_value('Chat de avance').run()
        at.selectbox(key='trab_chat_area_1').set_value('Faena').run()
        at.selectbox(key='trab_chat_activo_1').set_value(1).run()
        at.chat_input[0].set_value('Hallazgo en rodamiento').run()
        self.assertEqual(at.session_state['trab_chat_pendiente_1']['trabajo_id'],1)
        at.selectbox(key='trab_chat_area_1').set_value('Procesos').run()
        at.selectbox(key='trab_chat_activo_1').set_value(2).run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertEqual(at.session_state['trab_chat_pendiente_1']['trabajo_id'],1)
        self.assertNotIn('Reintentar guardar en este trabajo',[x.label for x in at.button])
        self.assertTrue(at.chat_input[0].disabled)

    def test_aclaracion_aparece_en_chat_sin_confirmacion(self):
        extra="""
m.db.ultima_novedad=lambda *a:dict(id=1,estado='pregunta',detalle='¿Se terminó la pega completa o solo el montaje?')
m.mostrar_trabajos()
"""
        at=AppTest.from_string(SCRIPT.replace('m.mostrar_trabajos()',extra)).run(timeout=15)
        at.radio(key='trab_vista').set_value('Chat de avance').run()
        at.selectbox(key='trab_chat_area_1').set_value('Faena').run()
        at.selectbox(key='trab_chat_activo_1').set_value(1).run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertTrue(any('solo el montaje' in x.value for x in at.markdown))
        self.assertNotIn('Confirmar actualización',[x.label for x in at.button])
        self.assertFalse(at.chat_input[0].disabled)

    def test_pruebas_visibles_y_dialogo_natural_con_observacion(self):
        extra="""
from motores.pruebas_trabajos import transicion
st.session_state['_trabajo_test']['estado']='Terminado'
st.session_state['_trabajo_test']['avance']=100
def prueba(correo,n,ident,version,accion,texto=''):
    cambio=transicion(st.session_state['_trabajo_test'],accion,texto)
    return actualizar(correo,n,ident,version,cambio,mensaje=texto or accion)
m.db.registrar_prueba=prueba
m.mostrar_trabajos()
"""
        at=AppTest.from_string(SCRIPT.replace('m.mostrar_trabajos()',extra)).run(timeout=15)
        at.radio(key='trab_vista').set_value('Chat de avance').run()
        at.selectbox(key='trab_chat_area_1').set_value('Faena').run()
        at.checkbox(key='trab_chat_incluir_terminados_1').set_value(True).run()
        at.selectbox(key='trab_chat_activo_1').set_value(1).run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertTrue(any('Prueba de funcionamiento' in x.value for x in at.subheader))
        at.button(key='trab_prueba_1_1_iniciar_prueba').click().run()
        self.assertEqual(at.session_state['_trabajo_test']['prueba'],'En prueba')
        at.chat_input[0].set_value('sí').run()
        self.assertEqual(at.session_state['_trabajo_test']['dialogo_prueba']['paso'],'descripcion')
        at.chat_input[0].set_value('Ruido fuerte en soporte').run()
        self.assertEqual(at.session_state['_trabajo_test']['dialogo_prueba']['paso'],'impacto')
        at.chat_input[0].set_value('sí').run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertEqual(at.session_state['_trabajo_test']['prueba'],'Fallida')
        self.assertIn('Ruido fuerte',at.session_state['_trabajo_test']['hallazgos'])

    def test_botones_area_abren_ejecucion_y_pruebas_con_detalle(self):
        extra="""
m.db.trabajos=lambda *a:[st.session_state['_trabajo_test'],dict(st.session_state['_trabajo_test'],id=2,descripcion='Montaje en proceso',estado='En ejecución',avance=50),dict(st.session_state['_trabajo_test'],id=3,descripcion='Rodamiento terminado sin prueba',estado='Terminado',avance=100),dict(st.session_state['_trabajo_test'],id=4,descripcion='Motor probado',estado='Terminado',avance=100,prueba='Aprobada',detalle_prueba='Normal'),dict(st.session_state['_trabajo_test'],id=5,area='Procesos',descripcion='Bomba de otra área',estado='Terminado',avance=100,prueba='Fallida',detalle_prueba='Ruido')]
m.mostrar_trabajos()
"""
        at=AppTest.from_string(SCRIPT.replace('m.mostrar_trabajos()',extra)).run(timeout=15)
        at.button(key='trab_pulso_1_0').click().run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        texto=' '.join(x.value for x in at.markdown)
        self.assertIn('Por completar · 2',texto)
        self.assertIn('Ejecución terminada · 2',texto)
        self.assertIn('Rodamiento terminado sin prueba',texto)
        self.assertNotIn('Bomba de otra área',texto)
        at.button(key='trab_detalle_pulso_1_cerrar').click().run()
        at.button(key='trab_pruebas_area_1_0').click().run()
        texto=' '.join(x.value for x in at.markdown)
        self.assertIn('Faltan por probar / en prueba · 3',texto)
        self.assertIn('Pruebas aprobadas · 1',texto)
        at.button(key='trab_detalle_pruebas_1_abrir_3').click().run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertEqual(at.radio(key='trab_vista').value,'Chat de avance')
        self.assertTrue(at.checkbox(key='trab_chat_incluir_terminados_1').value)
        self.assertEqual(at.selectbox(key='trab_chat_activo_1').value,3)

    def test_terminado_pregunta_pruebas_y_se_oculta_al_posponer(self):
        at=AppTest.from_string(SCRIPT).run(timeout=15)
        at.radio(key='trab_vista').set_value('Chat de avance').run()
        at.selectbox(key='trab_chat_area_1').set_value('Faena').run()
        self.assertTrue(any('🟡 Pendiente' in op for op in at.selectbox(key='trab_chat_activo_1').options))
        at.selectbox(key='trab_chat_activo_1').set_value(1).run()
        at.chat_input[0].set_value('trabajo terminado').run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertEqual(at.session_state['_trabajo_test']['estado'],'Terminado')
        self.assertEqual(at.selectbox(key='trab_chat_activo_1').value,1)
        self.assertTrue(any(x.label=='Sí, se realizaron' for x in at.button))
        at.button(key='trab_prueba_1_1_posponer_prueba').click().run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertEqual(at.session_state['_trabajo_test']['estado'],'Terminado')
        self.assertEqual(at.session_state['_trabajo_test']['prueba'],'Pendiente')
        self.assertEqual(at.selectbox(key='trab_chat_activo_1').value,0)
        self.assertFalse(at.checkbox(key='trab_chat_incluir_terminados_1').value)
        at.checkbox(key='trab_chat_incluir_terminados_1').set_value(True).run()
        self.assertTrue(any('🟢 Terminada' in op for op in at.selectbox(key='trab_chat_activo_1').options))
        at.selectbox(key='trab_chat_activo_1').set_value(1).run()
        at.chat_input[0].set_value('Comentario posterior al cierre de ejecución').run()
        self.assertEqual(at.session_state['_trabajo_test']['ultimo_mensaje'],'Comentario posterior al cierre de ejecución')

    def test_novedad_area_directa_y_sin_boton_sin_senal(self):
        extra="""
def guardar_area(*args,**kwargs):
    st.session_state['_area_guardada']=(args,kwargs)
    return 1
m.area_db.guardar=guardar_area
m.mostrar_trabajos()
"""
        at=AppTest.from_string(SCRIPT.replace('m.mostrar_trabajos()',extra)).run(timeout=15)
        at.radio(key='trab_vista').set_value('Chat de avance').run()
        at.selectbox(key='trab_chat_area_1').set_value('Faena').run()
        self.assertEqual(at.selectbox(key='trab_chat_activo_1').value,0)
        self.assertEqual(len(at.get('link_button')),0)
        at.chat_input[0].set_value('Hallazgo de seguridad en acceso del área').run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        args,kwargs=at.session_state['_area_guardada']
        self.assertEqual(args[:3],('sup@test.cl',1,'Faena'))
        self.assertEqual(kwargs['mensaje'],'Hallazgo de seguridad en acceso del área')
        self.assertEqual(at.session_state['_trabajo_test']['version'],1)

    def test_informe_incluye_novedad_area_y_nombres_de_actividades(self):
        extra="""
r=dict(id=7,area='Faena',mensaje='Calidad: producto expuesto en el acceso',categoria='Calidad',impacto='Partida',estado='Abierto',resuelve=None,nombre='Supervisor Dos',usuario='dos@test.cl',fecha='2026-10-18T12:00:00')
m.area_db.listar=lambda *a:[r]
def pdf(*args):
    st.session_state['_corte_pdf']=args[2]
    return b'%PDF-test'
m.generar_pdf=pdf
m.mostrar_trabajos()
"""
        at=AppTest.from_string(SCRIPT.replace('m.mostrar_trabajos()',extra)).run(timeout=15)
        at.radio(key='trab_vista').set_value('Reportes de turno').run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertIn('producto expuesto',at.text_area(key='trab_resumen_1_comentario').value)
        self.assertEqual(at.session_state['_corte_pdf']['novedades_area'][0]['nombre'],'Supervisor Dos')
        self.assertTrue(at.session_state['_corte_pdf']['sugerencias_automaticas'])

    def test_novedad_area_sin_automatico_ni_impacto(self):
        script=SCRIPT[:SCRIPT.index('m.mostrar_trabajos()')]+"m._chat_area(st.session_state['usuario_actual'],1,'Faena')"
        at=AppTest.from_string(script).run(timeout=15)
        self.assertEqual(len(at.exception),0,str(at.exception))
        tipo=next(x for x in at.selectbox if x.label=='Tipo de novedad')
        self.assertNotIn('Automática',tipo.options)
        self.assertFalse(any('Impacto' in x.label for x in at.selectbox))
        self.assertEqual(len(at.get('file_uploader')),1)

    def test_filtro_validacion_elimina_trabajo_al_aprobar_y_se_puede_salir(self):
        extra="""
from motores.pruebas_trabajos import transicion
def registrar(correo,n,ident,version,accion):
    actual=dict(st.session_state['_trabajo_test'])
    actual.update(transicion(actual,accion));actual['version']+=1
    st.session_state['_trabajo_test']=actual
m.db.registrar_prueba=registrar
m.mostrar_trabajos()
"""
        script=SCRIPT.replace("estado='Pendiente',avance=0", "estado='Terminado',avance=100").replace('m.mostrar_trabajos()',extra)
        at=AppTest.from_string(script).run(timeout=15)
        at.radio(key='trab_vista').set_value('Chat de avance').run()
        at.selectbox(key='trab_chat_area_1').set_value('Faena').run()
        at.toggle(key='trab_chat_solo_validacion_1').set_value(True).run()
        self.assertTrue(any('Rodamiento' in op for op in at.selectbox(key='trab_chat_activo_1').options))
        at.selectbox(key='trab_chat_activo_1').set_value(1).run()
        at.button(key='trab_prueba_1_1_iniciar_prueba').click().run()
        self.assertTrue(any('Rodamiento' in op for op in at.selectbox(key='trab_chat_activo_1').options))
        at.button(key='trab_prueba_1_1_sin_observaciones').click().run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertEqual(at.session_state['_trabajo_test']['prueba'],'Aprobada')
        self.assertFalse(any('Rodamiento' in op for op in at.selectbox(key='trab_chat_activo_1').options))
        self.assertTrue(any('No quedan trabajos pendientes de validación' in x.value for x in at.success))
        self.assertFalse(at.toggle(key='trab_chat_solo_validacion_1').disabled)
        at.toggle(key='trab_chat_solo_validacion_1').set_value(False).run()
        self.assertEqual(len(at.exception),0,str(at.exception))

    def test_criterio_validacion_con_fallida_y_exclusion_documentada(self):
        from modulos.trabajos import falta_validacion_funcionamiento as falta
        base=dict(estado='Terminado',prueba='Pendiente',detalle_prueba='')
        self.assertTrue(falta(base))
        self.assertTrue(falta(base|dict(prueba='Fallida')))
        self.assertTrue(falta(base|dict(prueba='No requerida')))
        self.assertFalse(falta(base|dict(prueba='No requerida',detalle_prueba='Según pauta no aplica')))
        self.assertFalse(falta(base|dict(prueba='Aprobada',dialogo_prueba={'paso':'','resultado':'Normal'})))
        self.assertFalse(falta(base|dict(estado='En ejecución')))

    def test_finalizar_posponer_retomar_y_aprobar_desde_filtro(self):
        at=AppTest.from_string(SCRIPT).run(timeout=15)
        at.radio(key='trab_vista').set_value('Chat de avance').run()
        at.selectbox(key='trab_chat_area_1').set_value('Faena').run()
        at.selectbox(key='trab_chat_activo_1').set_value(1).run()
        at.button(key='trab_chat_rapido_1_Trabajo terminado').click().run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertEqual(at.selectbox(key='trab_chat_activo_1').value,1)
        self.assertTrue(any('¿Se realizaron las pruebas' in x.value for x in at.markdown))
        at.button(key='trab_prueba_1_1_posponer_prueba').click().run()
        self.assertEqual(at.selectbox(key='trab_chat_activo_1').value,0)
        self.assertEqual(at.session_state['_trabajo_test']['prueba'],'Pendiente')
        at.toggle(key='trab_chat_solo_validacion_1').set_value(True).run()
        at.selectbox(key='trab_chat_activo_1').set_value(1).run()
        at.button(key='trab_prueba_1_1_iniciar_prueba').click().run()
        at.button(key='trab_prueba_1_1_sin_observaciones').click().run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertEqual(at.session_state['_trabajo_test']['prueba'],'Aprobada')
        self.assertFalse(any('Rodamiento' in op for op in at.selectbox(key='trab_chat_activo_1').options))

    def test_error_del_resumen_se_muestra_solo_a_administracion_y_se_conserva(self):
        extra="""
from ia import resumen_turno
from ia import diagnostico
from ia.cliente import ConfiguracionIA
diagnostico.obtener_configuracion=lambda:ConfiguracionIA('Gemini','clave-secreta-de-prueba','modelo-prueba')
def fallar(*args):raise RuntimeError('503 consulta falló api_key=clave-secreta-de-prueba')
resumen_turno.mejorar_resumen=fallar
m.generar_pdf=lambda *args:b'%PDF-test'
m.mostrar_trabajos()
"""
        for admin in [False,True]:
            script=SCRIPT.replace('m.mostrar_trabajos()',extra).replace('es_admin=False','es_admin='+str(admin))
            at=AppTest.from_string(script).run(timeout=15)
            at.radio(key='trab_vista').set_value('Reportes de turno').run()
            at.text_area(key='trab_resumen_1_comentario').set_value('Resumen manual conservado').run()
            next(b for b in at.button if b.label=='Analizar y sintetizar con GearBot').click().run()
            self.assertEqual(len(at.exception),0,str(at.exception))
            self.assertEqual(at.text_area(key='trab_resumen_1_comentario').value,'Resumen manual conservado')
            detalles=[x.value for x in at.code]
            self.assertEqual(bool(detalles),admin)
            if admin:
                self.assertIn('RuntimeError',detalles[0]);self.assertNotIn('clave-secreta-de-prueba',detalles[0])
            at.text_area(key='trab_resumen_1_comentario').set_value('Editado después del error').run()
            self.assertTrue(any('Referencia:' in x.value for x in at.warning))

    def test_galeria_recupera_y_muestra_cinco_fotos_guardadas(self):
        extra="""
from PIL import Image
from io import BytesIO
from datetime import datetime
fotos=[]
for i in range(5):
    out=BytesIO();Image.new('RGB',(60,40),(i*30,90,160)).save(out,format='PNG')
    fotos.append(dict(id=i+1,nombre='foto_'+str(i+1)+'.png',contenido=out.getvalue(),usuario='sup@test.cl',fecha=datetime(2026,10,18,12)))
st.session_state['_trabajo_test']['fotos']=[1,2,3,4,5]
m.db.evidencia=lambda *args:fotos
m._galeria_trabajo(st.session_state['usuario_actual'],1,st.session_state['_trabajo_test'])
"""
        at=AppTest.from_string(SCRIPT.replace('m.mostrar_trabajos()',extra)).run(timeout=15)
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertTrue(any('Fotos guardadas en esta actividad: 5' in x.value for x in at.caption))
        self.assertEqual(len(at.get('image')),5)

    def test_galeria_area_incluye_fotos_de_novedades_anteriores_a_las_ultimas_ocho(self):
        extra="""
from PIL import Image
from io import BytesIO
import base64
out=BytesIO();Image.new('RGB',(40,30),'orange').save(out,format='PNG')
contenido=base64.b64encode(out.getvalue()).decode()
registros=[dict(nombre='Supervisor',fecha='2026-10-18T12:00:00',fotos=[dict(nombre='area_'+str(i)+'.png',contenido=contenido)]) for i in range(10)]
m._galeria_area(registros)
"""
        at=AppTest.from_string(SCRIPT.replace('m.mostrar_trabajos()',extra)).run(timeout=15)
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertTrue(any('Fotos guardadas en las novedades de esta área: 10' in x.value for x in at.caption))
        self.assertEqual(len(at.get('image')),10)
