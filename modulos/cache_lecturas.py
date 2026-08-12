from __future__ import annotations
import streamlit as st
from database.metricas_sistema import resumen_uso_ia, uso_base_datos
from database.rendimiento import resumen_dashboard

@st.cache_data(ttl=20, show_spinner=False)
def dashboard_cache(): return resumen_dashboard()

@st.cache_data(ttl=30, show_spinner=False)
def uso_ia_cache(): return resumen_uso_ia()

@st.cache_data(ttl=90, show_spinner=False)
def almacenamiento_cache(): return uso_base_datos()
