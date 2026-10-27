import unittest
from pathlib import Path
from unittest.mock import patch
import streamlit as st
from streamlit.testing.v1 import AppTest
import neuralmant_ui

class ArranqueCloudTest(unittest.TestCase):
    def test_app_py_usa_runtime_existente_en_contexto_streamlit(self):
        with patch.object(neuralmant_ui,'main',lambda:st.write('Inicio de NeuralMant')):
            at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=15)
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertTrue(any('Inicio de NeuralMant' in e.value for e in at.markdown))
