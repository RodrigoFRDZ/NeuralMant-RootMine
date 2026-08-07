from pathlib import Path

import streamlit as st

from database.conexion import crear_tablas
from ia.cliente import obtener_configuracion
from modulos.acerca import mostrar_acerca
from modulos.historial import mostrar_historial
from modulos.base_conocimiento import mostrar_base_conocimiento
from modulos.indicadores import mostrar_indicadores
from modulos.inicio import mostrar_inicio
from modulos.nuevo_adf import mostrar_nuevo_adf

st.set_page_config(
    page_title="NeuralMant · RootMine",
    page_icon="assets/neuralmant_favicon.png",
    layout="wide",
    initial_sidebar_state="expanded",
)


def cargar_estilos() -> None:
    ruta = Path("assets/styles.css")
    if ruta.exists():
        st.markdown(f"<style>{ruta.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def inicializar_sesion() -> None:
    st.session_state.setdefault("usuario", "")
    st.session_state.setdefault("pagina", "🏠 Dashboard")
    st.session_state.setdefault("api_key_temporal", "")
    st.session_state.setdefault("proveedor_ia", "Gemini")
    st.session_state.setdefault("modelo_ia", "gemini-3.1-flash-lite")


def marca_compacta() -> None:
    logo, nombre = st.columns([0.34, 1], gap="small", vertical_alignment="center")
    with logo:
        st.image("assets/neuralmant_logo.png", use_container_width=True)
    with nombre:
        st.markdown(
            """
            <div class="brand-lockup-text">
              <div class="brand-name">Neural<span>Mant</span></div>
              <div class="brand-suite">SUITE</div>
              <div class="brand-module">ROOTMINE</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def mostrar_identificacion() -> None:
    izquierda, derecha = st.columns([1.05, 1], gap="large")
    with izquierda:
        st.image("assets/gearbot_hero.png", use_container_width=True)
    with derecha:
        logo_col, _ = st.columns([0.22, 0.78])
        with logo_col:
            st.image("assets/neuralmant_logo.png", use_container_width=True)
        st.markdown(
            """
            <div class="login-copy login-copy-compact">
              <div class="eyebrow">NEURALMANT</div>
              <h1>ROOT<span>MINE</span></h1>
              <h3>Análisis Inteligente de Causa Raíz</h3>
              <p>Descubriendo el origen de las fallas para evitar su recurrencia.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("identificacion"):
            st.subheader("Hola, soy GearBot 👋")
            nombre = st.text_input("¿Cómo te llamas?", placeholder="Ejemplo: Rodrigo Fernández")
            continuar = st.form_submit_button("Ingresar a RootMine →", type="primary", use_container_width=True)
        if continuar:
            nombre = nombre.strip()
            if len(nombre) < 3:
                st.error("Ingresa un nombre válido.")
            else:
                st.session_state.usuario = nombre
                st.rerun()
        st.markdown('<div class="creator-seal">Versión 3.0 · Created by <b>Rodrigo Fernández</b></div>', unsafe_allow_html=True)


def mostrar_menu() -> str:
    with st.sidebar:
        marca_compacta()
        st.caption("GearBot · Asistente de análisis inteligente")
        st.divider()
        st.markdown(f"**Hola, {st.session_state.usuario.split()[0]}**")

        opciones = ["🏠 Dashboard", "📝 RootMine · Nuevo ADF", "📚 Historial", "📊 Indicadores", "🧠 Base de conocimiento", "ℹ️ Acerca de"]
        pagina = st.radio("Navegación", opciones, index=opciones.index(st.session_state.pagina), label_visibility="collapsed")
        st.session_state.pagina = pagina

        st.divider()
        with st.expander("⚙️ Configuración IA", expanded=False):
            proveedor_anterior = st.session_state.proveedor_ia
            proveedor = st.selectbox("Proveedor", ["Gemini", "OpenAI"], index=0 if proveedor_anterior == "Gemini" else 1)
            if proveedor != proveedor_anterior:
                st.session_state.proveedor_ia = proveedor
                st.session_state.api_key_temporal = ""
                st.session_state.modelo_ia = "gemini-3.1-flash-lite" if proveedor == "Gemini" else "gpt-5.6"
                st.rerun()
            configuracion = obtener_configuracion()
            if configuracion.api_key:
                st.success(f"{proveedor} configurado")
            else:
                st.warning(f"Falta la clave de {proveedor}")
            st.session_state.api_key_temporal = st.text_input(
                f"Clave temporal de {proveedor}", value=st.session_state.api_key_temporal,
                type="password", help="Solo se conserva durante esta sesión.",
            ).strip()
            modelo_default = "gemini-3.1-flash-lite" if proveedor == "Gemini" else "gpt-5.6"
            st.session_state.modelo_ia = st.text_input("Modelo", value=st.session_state.modelo_ia).strip() or modelo_default

        if st.button("Cambiar usuario", use_container_width=True):
            st.session_state.usuario = ""
            st.session_state.pagina = "🏠 Dashboard"
            st.session_state.pop("nuevo_adf", None)
            st.rerun()

        st.markdown('<div class="sidebar-credit">NeuralMant Suite · RootMine v3.0<br>© 2026 Rodrigo Fernández</div>', unsafe_allow_html=True)
        return pagina


def main() -> None:
    cargar_estilos()
    crear_tablas()
    inicializar_sesion()
    if not st.session_state.usuario:
        mostrar_identificacion()
        return
    pagina = mostrar_menu()
    if pagina == "🏠 Dashboard": mostrar_inicio()
    elif pagina == "📝 RootMine · Nuevo ADF": mostrar_nuevo_adf()
    elif pagina == "📚 Historial": mostrar_historial()
    elif pagina == "📊 Indicadores": mostrar_indicadores()
    elif pagina == "🧠 Base de conocimiento": mostrar_base_conocimiento()
    else: mostrar_acerca()


if __name__ == "__main__":
    main()
