import unittest
from streamlit.testing.v1 import AppTest

SCRIPT = """
import streamlit as st
from modulos import inicio as m
st.session_state.setdefault('usuario','Rodrigo')
st.session_state.setdefault('usuario_actual',dict(correo='sol@test.cl',rol='tecnico',es_admin=False))
m.dashboard_cache=lambda:dict(aprobados=0,equipos=0,areas=0,con_ia=0,acciones=0)
m.borradores_livianos=lambda *a,**k:[]
m.correcciones_livianas=lambda *a,**k:[]
m.recientes_livianos=lambda *a,**k:[]
m.mostrar_inicio()
"""

class InicioTest(unittest.TestCase):
    def test_suite_solo_dos_modulos_sin_titulo_ni_panel_adf(self):
        at=AppTest.from_string(SCRIPT).run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        texto=' '.join(x.value for x in at.markdown)
        self.assertIn('Hola, Rodrigo.',texto)
        self.assertIn('¿En qué trabajaremos hoy?',texto)
        self.assertNotIn('Elige tu módulo',texto)
        self.assertNotIn('Panel general',texto)
        self.assertEqual(len(at.metric),0)
        self.assertEqual([b.label for b in at.button],['Entrar a RootMine →','Entrar a Gestión de Materiales →','Entrar a Seguimiento de trabajos →'])
        at.session_state['mat_vista']='Stock de seguridad'
        at.button(key='dash_materiales').click().run()
        self.assertEqual(at.session_state['pagina'],'📦 Gestión de Materiales')
        self.assertIsNone(at.session_state['mat_vista'])
        at.button(key='dash_rootmine').click().run()
        self.assertEqual(at.session_state['pagina'],'🧠 RootMine')

    def test_saludo_usa_nombre_de_cuenta_autenticada(self):
        script=SCRIPT.replace("dict(correo='sol@test.cl',rol='tecnico',es_admin=False)", "dict(nombre='Daniel Pérez',correo='sol@test.cl',rol='tecnico',es_admin=False)")
        at=AppTest.from_string(script).run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        texto=' '.join(x.value for x in at.markdown)
        self.assertIn('Hola, Daniel.',texto)
        self.assertNotIn('Hola, Rodrigo.',texto)

    def test_admin_tambien_ve_solo_dos_modulos(self):
        script=SCRIPT.replace("rol='tecnico',es_admin=False", "rol='ingeniero',es_admin=True")
        at=AppTest.from_string(script).run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertEqual(len(at.button),3)

    def test_rootmine_recupera_panel_y_accesos_originales(self):
        at=AppTest.from_string(SCRIPT.replace('m.mostrar_inicio()','m.mostrar_rootmine()')).run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertEqual(len(at.metric),5)
        self.assertIn('Panel general',' '.join(x.value for x in at.markdown))
        self.assertNotIn('dash_materiales',[b.key for b in at.button])
        for clave,pagina in [('hist','📚 Historial'),('ind','📊 Indicadores'),('planes','📋 Planes de acción')]:
            at.button(key='dash_'+clave).click().run()
            self.assertEqual(at.session_state['pagina'],pagina)
        at.button(key='dash_nuevo').click().run()
        self.assertEqual(at.session_state['pagina'],'📝 RootMine · Nuevo ADF')

    def test_navegacion_agrupa_herramientas_dentro_modulos(self):
        from neuralmant_ui import _opciones_navegacion
        u=dict(rol='jefe',es_admin=False)
        inicio=_opciones_navegacion(u,'🏠 Dashboard')
        self.assertNotIn('📚 Historial',inicio)
        self.assertNotIn('✅ Aprobaciones de materiales',inicio)
        for pagina in ['🧠 RootMine','📚 Historial','📋 Planes de acción']:
            opciones=_opciones_navegacion(u,pagina)
            self.assertIn('📚 Historial',opciones)
            self.assertIn('📊 Indicadores',opciones)
            self.assertIn('📋 Planes de acción',opciones)
        materiales=_opciones_navegacion(u,'✅ Aprobaciones de materiales')
        self.assertIn('✅ Aprobaciones de materiales',materiales)
        self.assertNotIn('📚 Historial',materiales)
