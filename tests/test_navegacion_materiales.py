import unittest
from modulos.notificaciones import folio_material
from streamlit.testing.v1 import AppTest

class NavegacionMaterialesTest(unittest.TestCase):
    def test_notificaciones_nuevas_legacy_y_otros_tipos(self):
        self.assertEqual(folio_material({'tipo':'materiales:12'}),12)
        self.assertEqual(folio_material({'tipo':'materiales','titulo':'Materiales #23 · Pendiente jefe'}),23)
        self.assertIsNone(folio_material({'tipo':'info','titulo':'Materiales #23'}))
        self.assertIsNone(folio_material({'tipo':'materiales:abc'}))

    def test_url_abre_solicitud_y_preserva_otros_parametros(self):
        script='''
import streamlit as st
from modulos.navegacion_materiales import abrir_material_desde_url
abrir_material_desde_url()
st.write(st.session_state.get('pagina'))
st.write(st.session_state.get('mat_solicitud_enlace'))
'''
        at=AppTest.from_string(script)
        at.query_params['solicitud_material']='31'
        at.query_params['otro']='conservar'
        at.run(timeout=15)
        self.assertEqual(len(at.exception),0)
        self.assertEqual(at.session_state['pagina'],'📦 Gestión de Materiales')
        self.assertEqual(at.session_state['mat_solicitud_enlace'],31)
        self.assertNotIn('solicitud_material',at.query_params)
        self.assertIn('otro',at.query_params)

if __name__=='__main__':unittest.main()
