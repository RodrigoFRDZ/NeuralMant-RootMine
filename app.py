"""Streamlit 1.65 entry point: UI and offline routes share the same origin."""
import streamlit as st
from campo.api import routes, marcar_rutas_registradas
from streamlit import config

app = st.App('neuralmant_ui.py', routes=routes(config.get_option('server.baseUrlPath') or ''))
marcar_rutas_registradas()


if __name__ == '__main__':
    app.run()
