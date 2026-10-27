"""Optional ASGI launcher for self-hosted deployments, separate from Cloud app.py."""
import streamlit as st
from streamlit import config
from campo.api import routes, marcar_rutas_registradas

app = st.App('neuralmant_ui.py', routes=routes(config.get_option('server.baseUrlPath') or ''))
marcar_rutas_registradas()

if __name__ == '__main__':
    app.run()
