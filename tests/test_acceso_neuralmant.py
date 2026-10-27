import unittest
from streamlit.testing.v1 import AppTest

SCRIPT="""
import streamlit as st
import neuralmant_ui as a
a.resumen_maestro=lambda:{'total':101}
st.session_state.setdefault('login_pendiente',None)
a.mostrar_identificacion()
"""
class AccesoNeuralMantTest(unittest.TestCase):
    def test_ingreso_neuralmant_con_gearbot_correo(self):
        at=AppTest.from_string(SCRIPT).run(timeout=15)
        self.assertEqual(len(at.exception),0,str(at.exception))
        html=' '.join(x.value for x in at.markdown)
        self.assertIn('NEURAL<span>MANT</span>',html)
        self.assertIn('Soy GearBot. Bienvenido a NeuralMant.',html)
        self.assertNotIn('ROOT<span>MINE</span>',html)
        self.assertIn('Ingresar a NeuralMant →',[b.label for b in at.button])
        self.assertIn('Correo Agrosuper',[x.label for x in at.text_input])
    def test_clave_para_perfil_que_aplica(self):
        script=SCRIPT.replace("st.session_state.setdefault('login_pendiente',None)", "a.tiene_llave=lambda correo:True\nst.session_state['login_pendiente']=dict(nombre='Jefe',correo='jefe@test.cl',rol='jefe')")
        at=AppTest.from_string(script).run(timeout=15)
        self.assertEqual(len(at.exception),0,str(at.exception))
        clave=next(x for x in at.text_input if x.label=='Clave de acceso')
        self.assertEqual(clave.proto.DESCRIPTOR.fields_by_name['type'].enum_type.values_by_number[clave.proto.type].name,'PASSWORD')
        correo=next(x for x in at.text_input if x.label=='Correo corporativo')
        self.assertEqual(correo.value,'jefe@test.cl')
        self.assertTrue(correo.disabled)
