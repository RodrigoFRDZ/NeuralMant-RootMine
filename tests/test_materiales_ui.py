import sys
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SCRIPT = '''
import streamlit as st
from modulos import materiales as m
m.sincronizar_flujo_stock = lambda correo: None
m.listar = lambda correo: st.session_state.get('_registros_test', [])
m.cargar_centros = lambda: {'1802': 'San Vicente'}
m.cargar_usuarios = lambda: []
st.session_state.setdefault('usuario_actual', {'correo':'admin@test.cl', 'nombre':'Administrador', 'centro':'1802', 'area':'FAENA', 'rol':'ingeniero', 'es_admin':True})
m.mostrar_materiales()
'''

class MaterialesUITest(unittest.TestCase):
    def app(self):
        return AppTest.from_string(SCRIPT).run(timeout=15)
    def assert_clean(self, at):
        self.assertEqual(len(at.exception), 0, str(at.exception))
    def test_cuatro_vistas_y_mrp_simple(self):
        at=self.app();self.assert_clean(at)
        self.assertEqual(len(at.text_input),0)
        self.assertEqual(len(at.number_input),0)
        self.assertNotIn('Enviar al jefe de área',[b.label for b in at.button])
        abrir=[b for b in at.button if b.label=='Abrir']
        self.assertEqual(len(abrir),4)
        at.button(key='mat_ventana_Incorporación al MRP').click().run()
        self.assert_clean(at)
        self.assertIn('Guardar material para MRP',[b.label for b in at.button])
        self.assertNotIn('Justificación de la necesidad *',[t.label for t in at.text_area])
        self.assertNotIn('Referencias de respaldo',[t.label for t in at.text_area])
        self.assertNotIn('Jefe de área',[t.label for t in at.selectbox])
        at.button(key='mat_ventana_Seguimiento y aprobaciones').click().run()
        self.assert_clean(at)
        self.assertIn('Situación',[t.label for t in at.selectbox])
    def test_guia_no_clasifica_sin_contexto_criterios(self):
        at=self.app()
        at.button(key='mat_ventana_Guía de criticidad').click().run()
        self.assert_clean(at)
        self.assertFalse(any('Criticidad sugerida:' in x.value for x in at.success))
        for k in ['smac','co','te','ma']:
            at.selectbox(key='guia_independiente_'+k).set_value(2)
        at.run();self.assert_clean(at)
        self.assertTrue(any('Criticidad sugerida: B' in x.value for x in at.success))
        at.checkbox(key='guia_independiente_m').check().run()
        self.assert_clean(at)
        self.assertTrue(any('Categoría M' in x.value for x in at.info))
    def test_guia_ia_propuesta_revisable(self):
        script=SCRIPT.replace('m.mostrar_materiales()', '''
m._generar = lambda sistema, contexto, esquema: esquema(smac=3, co=1, te=None, ma=1, m_rotativo=False, estrategico=False, fundamento='Impacto directo declarado.', antecedentes_faltantes=['¿Cuál es el plazo de entrega?'])
m.mostrar_materiales()
''')
        at=AppTest.from_string(script).run(timeout=15)
        at.button(key='mat_ventana_Guía de criticidad').click().run()
        at.text_area(key='guia_independiente_contexto').set_value('Repuesto del eje; si falta detiene la línea, sin riesgo de seguridad. Sin sustituto.').run()
        at.button(key='guia_independiente_ia_criticidad').click().run()
        self.assert_clean(at)
        self.assertIsNone(at.selectbox(key='guia_independiente_co').value)
        at.button(key='guia_independiente_usar_criticidad').click().run()
        self.assert_clean(at)
        self.assertEqual(at.selectbox(key='guia_independiente_co').value,1)
        self.assertIsNone(at.selectbox(key='guia_independiente_te').value)
        self.assertFalse(any('Criticidad sugerida:' in x.value for x in at.success))
        at.selectbox(key='guia_independiente_te').set_value(2).run()
        self.assertTrue(any('Criticidad sugerida: A' in x.value for x in at.success))

    def test_area_desplegable_sin_cargo_en_stock_y_mrp(self):
        script=SCRIPT.replace("'area':'FAENA'", "'area':'Ingeniero mantenimiento'")
        at=AppTest.from_string(script).run(timeout=15)
        at.button(key='mat_ventana_Stock de seguridad').click().run()
        area=at.selectbox(key='mat_ss_0_area')
        self.assertIsNone(area.value)
        self.assertNotIn('Ingeniero mantenimiento',area.options)
        self.assertIn('Faena',area.options)
        self.assertIn('Elaborados',area.options)
        at.button(key='mat_ventana_Incorporación al MRP').click().run()
        self.assert_clean(at)
        area=at.selectbox(key='mat_mrp_0_area')
        self.assertIsNone(area.value)
        self.assertNotIn('Ingeniero mantenimiento',area.options)
        self.assertNotIn('Área *',[t.label for t in at.text_input])

    def app_con_guardado(self):
        script = SCRIPT.replace('m.mostrar_materiales()', """
from database.materiales import _validar
def guardar_test(correo, tipo, datos, responsables, enviar=False, **kwargs):
    _validar(datos, tipo, completo=enviar)
    st.session_state.setdefault('_guardados_test', []).append(dict(datos))
    return len(st.session_state['_guardados_test'])
m.guardar = guardar_test
m.mostrar_materiales()
""")
        at=AppTest.from_string(script).run(timeout=15)
        at.button(key='mat_ventana_Stock de seguridad').click().run()
        return at

    def completar_formulario(self, at, prefijo, stock):
        at.text_input(key=prefijo+'codigo').set_value('000123')
        at.text_input(key=prefijo+'desc').set_value('Rodamiento')
        at.text_input(key=prefijo+'um').set_value('UN')
        if stock:
            at.selectbox(key=prefijo+'almacen').set_value('M010')
        else:
            at.text_input(key=prefijo+'almacen').set_value('1000')
        at.text_input(key=prefijo+'equipos').set_value('Equipo 123')
        at.selectbox(key=prefijo+'area').set_value('Faena')
        if not stock:
            at.selectbox(key=prefijo+'crit').set_value('A')
        if stock:
            for k,v in [('smac',3),('co',1),('te',2),('ma',2)]:
                at.selectbox(key=prefijo+'guia_'+k).set_value(v)
            at.number_input(key=prefijo+'precio_unitario').set_value(100.)
            at.number_input(key=prefijo+'cant').set_value(2.0)
            at.text_area(key=prefijo+'justificacion').set_value('Detiene la línea si falta')
            at.text_area(key=prefijo+'respaldo').set_value('OT 123')
        at.run()

    def test_limpieza_envio_stock_y_no_reenvio_vacio(self):
        at=self.app_con_guardado()
        self.completar_formulario(at,'mat_ss_0_',True)
        at.button(key='mat_ss_0_enviar').click().run()
        self.assert_clean(at)
        for k in ['codigo','desc','um','equipos']:
            self.assertEqual(at.text_input(key='mat_ss_0_'+k).value,'')
        self.assertEqual(at.text_area(key='mat_ss_0_justificacion').value,'')
        self.assertEqual(at.text_area(key='mat_ss_0_respaldo').value,'')
        self.assertEqual(at.number_input(key='mat_ss_0_cant').value,0)
        self.assertIsNone(at.selectbox(key='mat_ss_0_area').value)
        self.assertEqual(at.selectbox(key='mat_ss_0_almacen').value,'M010')
        self.assertEqual(at.number_input(key='mat_ss_0_precio_unitario').value,0)
        self.assertIsNone(at.selectbox(key='mat_ss_0_guia_co').value)
        at.button(key='mat_ss_0_enviar').click().run()
        self.assertEqual(len(at.session_state['_guardados_test']),1)
        self.assertTrue(len(at.error)>0)

    def test_limpieza_mrp_y_conservacion_borrador_error(self):
        at=self.app_con_guardado()
        at.button(key='mat_ventana_Incorporación al MRP').click().run()
        self.completar_formulario(at,'mat_mrp_0_',False)
        at.button(key='mat_mrp_0_enviar').click().run()
        self.assert_clean(at)
        self.assertEqual(at.text_input(key='mat_mrp_0_codigo').value,'')
        self.assertIsNone(at.selectbox(key='mat_mrp_0_area').value)
        at.text_input(key='mat_mrp_0_codigo').set_value('456').run()
        at.button(key='mat_mrp_0_enviar').click().run()
        self.assertEqual(at.text_input(key='mat_mrp_0_codigo').value,'456')
        self.assertEqual(len(at.session_state['_guardados_test']),1)
        at.button(key='mat_mrp_0_guardar').click().run()
        self.assertEqual(at.text_input(key='mat_mrp_0_codigo').value,'456')
        self.assertEqual(len(at.session_state['_guardados_test']),2)

    def test_bandeja_y_acceso_directo_no_duplican_widgets(self):
        from datetime import datetime
        at=self.app()
        at.session_state['usuario_actual']={'correo':'jefe@test.cl','nombre':'Jefe','rol':'jefe','centro':'1802','area':'FAENA','es_admin':False}
        def fila(n):
            return dict(id=n,tipo='Stock de seguridad',estado='Pendiente jefe',version=1,material=str(n),centro='1802',area='FAENA',solicitante_nombre='Técnico',solicitante_email='sol@test.cl',jefe_email='jefe@test.cl',analista_email='rfernandezc@agrosuper.com',subgerente_email='cvelasquez@agrosuper.com',datos={'descripcion':'Rodamiento','unidad':'UN','criticidad':'A'},historial=[],fecha_envio=datetime.utcnow(),fecha_carga=None)
        at.session_state['_registros_test']=[fila(1),fila(2)]
        at.session_state['mat_vista']='Seguimiento y aprobaciones'
        at.session_state['mat_solicitud_enlace']=2
        at.run();self.assert_clean(at)
        self.assertEqual(at.selectbox(key='mat_aprobacion_abrir').value,2)
        self.assertTrue(any('Mis aprobaciones (2)' in t.label for t in at.tabs))
        at.session_state['mat_solicitud_enlace']=99
        at.run();self.assert_clean(at)
        self.assertTrue(any('no está disponible' in w.value for w in at.warning))

    def test_stock_almacenes_guia_integrada_impacto_desde_envio(self):
        at=self.app_con_guardado()
        self.completar_formulario(at,'mat_ss_0_',True)
        self.assert_clean(at)
        self.assertEqual(at.selectbox(key='mat_ss_0_almacen').options,
            ['M010 · Repuestos','M100 · Renovación, motores y bombas'])
        self.assertNotIn('Ayuda para asignar criticidad',[x.label for x in at.expander])
        self.assertEqual({x.label:x.value for x in at.metric}['Monto total de stock solicitado'],'200.00 USD')
        at.button(key='mat_ss_0_enviar').click().run()
        d=at.session_state['_guardados_test'][0]
        self.assertEqual(d['criticidad'],'A')
        self.assertEqual(d['precio_unitario'],100.)
        self.assertEqual(d['guia']['co'],1)
        script="from modulos import materiales as m\nm._impacto_solicitud("+repr(d)+")"
        aprobador=AppTest.from_string(script).run()
        self.assert_clean(aprobador)
        self.assertEqual({x.label:x.value for x in aprobador.metric}['Monto total de stock solicitado'],'200.00 USD')
        evaluacion=AppTest.from_string("from modulos import materiales as m\nm._evaluacion("+repr(dict(id=1,version=1,tipo='Stock de seguridad',datos=d))+")").run()
        self.assert_clean(evaluacion)
        self.assertEqual(len(evaluacion.number_input),1)
        self.assertEqual(evaluacion.number_input[0].label,'Valor del stock total actual de la bodega')

    def test_porcentaje_visible_antes_y_despues_valoracion(self):
        d=dict(cantidad=2,precio_unitario=100,moneda='USD',unidad='UN')
        def vista(datos):
            at=AppTest.from_string("from modulos import materiales as m\nm._impacto_solicitud("+repr(datos)+")").run()
            self.assert_clean(at)
            return {x.label:x.value for x in at.metric}
        self.assertEqual(vista(d)['Impacto sobre bodega actual'],'Pendiente de valorización')
        self.assertEqual(vista(d|{'analisis':{'valor_bodega':10000}})['Impacto sobre bodega actual'],'2.00%')
        self.assertEqual(vista(dict(cantidad=2,unidad='UN',analisis=dict(precio=100,moneda='USD',valor_bodega=10000)))['Impacto sobre bodega actual'],'2.00%')

    def test_validacion_solo_bodega_y_resumen_subgerente(self):
        script = """
import streamlit as st
from modulos import materiales as m
r={'id':1,'version':1,'tipo':'Stock de seguridad','datos':{'criticidad':'A','unidad':'UN','cantidad':6,'precio_unitario':100,'moneda':'USD'}}
a=m._evaluacion(r,clave='prueba')
st.session_state['_analisis_test']=a
"""
        at=AppTest.from_string(script).run(timeout=15)
        self.assert_clean(at)
        self.assertEqual(len(at.number_input),1)
        self.assertEqual(len(at.text_area),0)
        self.assertEqual(len(at.checkbox),0)
        at.number_input(key='eval_prueba_1_1_valor_bodega').set_value(10000.).run()
        self.assert_clean(at)
        valores={x.label:x.value for x in at.metric}
        self.assertEqual(valores['Aumento previsto del stock valorado'],'600.00 USD')
        self.assertEqual(valores['Aumento sobre la bodega actual'],'6.00%')
        self.assertEqual(valores['Stock valorado proyectado de bodega'],'10,600.00 USD')
        a=at.session_state['_analisis_test']
        vista=AppTest.from_string("from modulos import materiales as m\nm._resumen_valorizacion("+repr(a)+")").run()
        self.assert_clean(vista)
        self.assertEqual({x.label:x.value for x in vista.metric},valores)

if __name__=='__main__':unittest.main()
