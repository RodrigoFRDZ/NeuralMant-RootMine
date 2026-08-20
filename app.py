from pathlib import Path
from datetime import datetime, timedelta

import streamlit as st
import extra_streamlit_components as stx

from database.conexion import crear_tablas, descripcion_backend, usando_nube
from database.usuarios import buscar_usuario_por_correo, resumen_maestro, etiqueta_rol, inicializar_maestro_usuarios
from database.llaves_acceso import crear_llave, requiere_llave, tiene_llave, validar_llave
from database.sesiones import crear_sesion, validar_y_tocar_sesion, cerrar_sesion
from ia.cliente import obtener_configuracion
from modulos.acerca import mostrar_acerca
from modulos.historial import mostrar_historial
from modulos.base_conocimiento import mostrar_base_conocimiento
from modulos.indicadores import mostrar_indicadores
from modulos.planes_accion import mostrar_planes_accion
from modulos.inicio import mostrar_inicio
from modulos.nuevo_adf import mostrar_nuevo_adf, cargar_borrador_para_continuar
from modulos.validaciones import mostrar_validaciones
from modulos.notificaciones import mostrar_campana
from modulos.administracion import mostrar_administracion

st.set_page_config(
    page_title="NeuralMant · RootMine",
    page_icon="assets/neuralmant_favicon.png",
    layout="wide",
    initial_sidebar_state="expanded",
)


COOKIE_SESION = "rootmine_session"
COOKIE_PAGINA = "rootmine_page"
COOKIE_BORRADOR = "rootmine_draft"
_COOKIE_MANAGER = None


def _cookie_manager():
    """Una sola instancia por ejecución para leer/escribir cookies del navegador."""
    global _COOKIE_MANAGER
    if _COOKIE_MANAGER is None:
        _COOKIE_MANAGER = stx.CookieManager(key="rootmine_cookie_manager")
    return _COOKIE_MANAGER


def _leer_cookie(nombre: str) -> str:
    try:
        return str(_cookie_manager().get(nombre) or "").strip()
    except Exception:
        return ""


def _guardar_cookie(nombre: str, valor: str, *, max_age: int = 43200) -> None:
    """Guarda solo si cambió, evitando reruns innecesarios del componente."""
    valor = str(valor or "")
    try:
        manager = _cookie_manager()
        actual = str(manager.get(nombre) or "")
        if actual == valor:
            return
        manager.set(
            nombre,
            valor,
            key=f"set_{nombre}_{abs(hash(valor)) % 10_000_000}",
            path="/",
            max_age=max_age,
            secure=True,
            same_site="strict",
        )
    except Exception:
        pass


def _borrar_cookie(nombre: str) -> None:
    try:
        manager = _cookie_manager()
        if manager.get(nombre) is not None:
            manager.delete(nombre, key=f"delete_{nombre}")
    except Exception:
        pass




@st.cache_resource(show_spinner=False)
def preparar_backend() -> bool:
    crear_tablas()
    inicializar_maestro_usuarios()
    return True

def es_admin_rootmine(usuario: dict) -> bool:
    return bool(usuario.get("es_admin", False))




def cargar_estilos() -> None:
    ruta = Path("assets/styles.css")
    if ruta.exists():
        st.markdown(f"<style>{ruta.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def inicializar_sesion() -> None:
    st.session_state.setdefault("usuario", "")
    st.session_state.setdefault("usuario_actual", None)
    st.session_state.setdefault("pagina", "🏠 Dashboard")
    st.session_state.setdefault("login_pendiente", None)
    st.session_state.setdefault("token_sesion", "")
    st.session_state.setdefault("ultimo_toque_sesion", None)
    # Evita que las cookies interfieran con los botones en cada rerun.
    # Se leen una sola vez al reconstruir la sesión después de F5.
    st.session_state.setdefault("_contexto_browser_restaurado", False)
    st.session_state.setdefault("_cookie_pagina_cache", None)
    st.session_state.setdefault("_cookie_borrador_cache", None)


def marca_compacta() -> None:
    logo, nombre = st.columns([0.52, 1], gap="small", vertical_alignment="center")
    with logo:
        st.image("assets/neuralmant_logo_sidebar_crisp.png", use_container_width=True)
    with nombre:
        st.markdown(
            """
            <div class="brand-lockup-text">
              <div class="brand-name">Neural<span>Mant</span></div>
              <div class="brand-suite">SUITE</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("ROOTMINE", key="brand_home", help="Volver al menú principal", use_container_width=True):
            st.session_state.pagina = "🏠 Dashboard"
            st.session_state.pop("nuevo_adf", None)
            st.rerun()



def barra_inicio(pagina: str) -> None:
    """Muestra un acceso consistente al Dashboard en todas las páginas internas."""
    if pagina == "🏠 Dashboard":
        return
    etiqueta = pagina.split("·")[-1].strip() if "·" in pagina else pagina
    etiqueta = etiqueta.lstrip("📝✅📚📊🧠🔐ℹ️ " ).strip()
    col_home, col_ruta = st.columns([0.22, 0.78], vertical_alignment="center")
    with col_home:
        if st.button("🏠 ROOTMINE · Inicio", key="top_home_button", help="Volver al menú principal", use_container_width=True):
            st.session_state.pagina = "🏠 Dashboard"
            st.session_state.pop("nuevo_adf", None)
            st.rerun()
    with col_ruta:
        st.markdown(f'<div class="rootmine-breadcrumb">ROOTMINE <span>›</span> {etiqueta}</div>', unsafe_allow_html=True)
    st.markdown('<div class="rootmine-top-divider"></div>', unsafe_allow_html=True)

def _token_sesion_actual() -> str:
    """Obtiene el token local o el token persistente del navegador.

    El token nunca se coloca en la URL.
    """
    token_estado = str(st.session_state.get("token_sesion") or "").strip()
    if token_estado:
        return token_estado
    return _leer_cookie(COOKIE_SESION)


def _guardar_token_sesion(token: str) -> None:
    token = str(token or "").strip()
    st.session_state.token_sesion = token
    if token:
        _guardar_cookie(COOKIE_SESION, token)
    try:
        # Limpia el parámetro legado de versiones antiguas, si alguien abre un link viejo.
        if "rm_session" in st.query_params:
            del st.query_params["rm_session"]
    except Exception:
        pass


def _limpiar_token_sesion() -> None:
    st.session_state.token_sesion = ""
    _borrar_cookie(COOKIE_SESION)
    _borrar_cookie(COOKIE_PAGINA)
    _borrar_cookie(COOKIE_BORRADOR)
    try:
        if "rm_session" in st.query_params:
            del st.query_params["rm_session"]
    except Exception:
        pass


def _persistir_contexto_navegacion(pagina: str) -> None:
    """Actualiza cookies solo cuando cambia realmente página o borrador.

    No consulta cookies en cada rerun; usa una copia en session_state.
    Esto evita que un componente de cookies interrumpa acciones de botones.
    """
    pagina = pagina or "🏠 Dashboard"
    if st.session_state.get("_cookie_pagina_cache") != pagina:
        _guardar_cookie(COOKIE_PAGINA, pagina)
        st.session_state["_cookie_pagina_cache"] = pagina

    datos = st.session_state.get("nuevo_adf") or {}
    borrador_actual = ""
    if (
        pagina == "📝 RootMine · Nuevo ADF"
        and datos.get("id_guardado")
        and datos.get("estado_validacion") == "Borrador"
    ):
        borrador_actual = str(datos["id_guardado"])

    if st.session_state.get("_cookie_borrador_cache") != borrador_actual:
        if borrador_actual:
            _guardar_cookie(COOKIE_BORRADOR, borrador_actual)
        else:
            _borrar_cookie(COOKIE_BORRADOR)
        st.session_state["_cookie_borrador_cache"] = borrador_actual


def restaurar_contexto_navegacion() -> None:
    """Restaura página/borrador UNA sola vez después de F5.

    En reruns posteriores no vuelve a imponer la cookie sobre la navegación
    elegida por el usuario.
    """
    if not st.session_state.get("usuario_actual"):
        return
    if st.session_state.get("_contexto_browser_restaurado"):
        return

    pagina_cookie = _leer_cookie(COOKIE_PAGINA)
    borrador_cookie = _leer_cookie(COOKIE_BORRADOR)

    st.session_state["_cookie_pagina_cache"] = pagina_cookie or "🏠 Dashboard"
    st.session_state["_cookie_borrador_cache"] = borrador_cookie or ""

    if pagina_cookie:
        st.session_state.pagina = pagina_cookie

    if (
        st.session_state.pagina == "📝 RootMine · Nuevo ADF"
        and not st.session_state.get("nuevo_adf")
        and borrador_cookie.isdigit()
    ):
        if not cargar_borrador_para_continuar(int(borrador_cookie)):
            st.session_state["_cookie_borrador_cache"] = ""

    st.session_state["_contexto_browser_restaurado"] = True


def cerrar_sesion_rootmine() -> None:
    """Cierra en Supabase, limpia cookies del navegador y estado sensible."""
    token = _token_sesion_actual()
    if token:
        try:
            cerrar_sesion(token)
        except Exception:
            # Aunque Supabase no responda, la sesión del navegador se elimina.
            pass

    _limpiar_token_sesion()

    claves_sesion = [
        "usuario", "usuario_actual", "login_pendiente", "nuevo_adf",
        "token_sesion", "ultimo_toque_sesion", "pagina",
        "confirmar_eliminar_borrador", "_contexto_browser_restaurado",
        "_cookie_pagina_cache", "_cookie_borrador_cache",
    ]
    for clave in claves_sesion:
        st.session_state.pop(clave, None)

    st.session_state.pagina = "🏠 Dashboard"


def restaurar_sesion_persistente() -> None:
    """Restaura tras F5 y renueva actividad como máximo cada 5 minutos."""
    token = _token_sesion_actual()
    if not token:
        return
    ahora = datetime.now()
    if st.session_state.get("usuario_actual"):
        ultimo = st.session_state.get("ultimo_toque_sesion")
        if ultimo and (ahora - ultimo) < timedelta(minutes=5):
            return
        correo = validar_y_tocar_sesion(token)
        if correo:
            st.session_state.ultimo_toque_sesion = ahora
            return
        st.session_state.usuario = ""; st.session_state.usuario_actual = None; st.session_state.login_pendiente = None; _limpiar_token_sesion(); return
    correo = validar_y_tocar_sesion(token)
    if not correo:
        st.session_state.usuario = ""; st.session_state.usuario_actual = None; st.session_state.login_pendiente = None; _limpiar_token_sesion(); return
    usuario = buscar_usuario_por_correo(correo)
    if not usuario:
        cerrar_sesion(token); st.session_state.usuario = ""; st.session_state.usuario_actual = None; _limpiar_token_sesion(); return
    st.session_state.token_sesion = token
    st.session_state.usuario_actual = usuario
    st.session_state.usuario = usuario["nombre"]
    st.session_state.login_pendiente = None
    st.session_state.ultimo_toque_sesion = ahora

def _completar_login(usuario: dict) -> None:
    token = crear_sesion(usuario.get("correo", ""))
    st.session_state.usuario_actual = usuario
    st.session_state.usuario = usuario["nombre"]
    st.session_state.login_pendiente = None
    st.session_state.ultimo_toque_sesion = datetime.now()
    # Login nuevo: arranca limpio. La restauración de cookies se reserva para F5.
    st.session_state["_contexto_browser_restaurado"] = True
    st.session_state["_cookie_pagina_cache"] = "🏠 Dashboard"
    st.session_state["_cookie_borrador_cache"] = ""
    _guardar_token_sesion(token)
    _guardar_cookie(COOKIE_PAGINA, "🏠 Dashboard")
    _borrar_cookie(COOKIE_BORRADOR)
    st.rerun()


def mostrar_identificacion() -> None:
    st.markdown('<div class="login-shell-marker"></div>', unsafe_allow_html=True)
    izquierda, derecha = st.columns([1.08, 1], gap="large", vertical_alignment="center")

    with izquierda:
        bot_col, _ = st.columns([0.82, 0.18])
        with bot_col:
            st.image("assets/gearbot_hero.png", use_container_width=True)
        st.markdown(
            """
            <div class="rootmine-login-brand">
              <div class="rootmine-login-name">ROOT<span>MINE</span></div>
              <div class="rootmine-login-subtitle">Análisis Inteligente de Causa Raíz</div>
              <div class="rootmine-login-copy">Conocimiento técnico, trazabilidad y validación en un solo flujo.</div>
              <div class="rootmine-features">
                <div><b>🧠</b><span>INTELIGENCIA<br>ARTIFICIAL</span></div>
                <div><b>🛡️</b><span>TRAZABILIDAD<br>TOTAL</span></div>
                <div><b>🔎</b><span>ANÁLISIS<br>PROFUNDO</span></div>
                <div><b>📋</b><span>MEJORA<br>CONTINUA</span></div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with derecha:
        logo_col, espacio = st.columns([0.46, 0.54])
        with logo_col:
            st.image("assets/neuralmant_login_lockup.png", use_container_width=True)

        pendiente = st.session_state.get("login_pendiente")
        if not pendiente:
            with st.form("identificacion"):
                st.markdown('<div class="login-form-title">Ingreso corporativo</div>', unsafe_allow_html=True)
                correo = st.text_input("Correo Agrosuper", placeholder="nombre@agrosuper.com")
                continuar = st.form_submit_button("Ingresar a RootMine →", type="primary", use_container_width=True)
            if continuar:
                correo = correo.strip().lower()
                usuario = buscar_usuario_por_correo(correo)
                if not usuario:
                    st.error("Este correo no está habilitado en el maestro de usuarios de RootMine.")
                elif requiere_llave(usuario):
                    st.session_state.login_pendiente = usuario
                    st.rerun()
                else:
                    _completar_login(usuario)
        else:
            nombre = pendiente.get("nombre", "Usuario")
            rol = etiqueta_rol(pendiente.get("rol", ""))
            correo = pendiente.get("correo", "")
            st.markdown('<div class="login-form-title">Acceso de validador</div>', unsafe_allow_html=True)
            st.caption(f"{nombre} · {rol}")

            if tiene_llave(correo):
                st.info("🔐 Este perfil requiere una llave personal para ingresar y validar ADF.")
                with st.form("validar_llave_acceso"):
                    llave = st.text_input("Llave de acceso", type="password")
                    entrar = st.form_submit_button("Validar e ingresar →", type="primary", use_container_width=True)
                if entrar:
                    if validar_llave(correo, llave):
                        _completar_login(pendiente)
                    else:
                        st.error("La llave de acceso no es correcta.")
            else:
                st.warning("🔑 Primer ingreso como validador: crea tu llave personal. La necesitarás en los próximos accesos.")
                with st.form("crear_llave_acceso"):
                    llave1 = st.text_input("Crear llave", type="password", help="Mínimo 6 caracteres")
                    llave2 = st.text_input("Repetir llave", type="password")
                    crear = st.form_submit_button("Crear llave e ingresar →", type="primary", use_container_width=True)
                if crear:
                    if llave1 != llave2:
                        st.error("Las llaves no coinciden.")
                    else:
                        try:
                            crear_llave(correo, llave1)
                            st.success("Llave creada correctamente.")
                            _completar_login(pendiente)
                        except Exception as error:
                            st.error(str(error))

            if st.button("← Usar otro correo", use_container_width=True):
                st.session_state.login_pendiente = None
                st.rerun()

        st.markdown(
            '<div class="login-access-note">ⓘ &nbsp;Acceso permitido solo para cuentas corporativas registradas.<br>'
            '<span>Los perfiles validadores utilizan además una llave personal.</span></div>',
            unsafe_allow_html=True,
        )
        resumen = resumen_maestro()
        st.markdown(f'<div class="login-master">👥 &nbsp;Maestro v4.2.5 · {resumen["total"]} usuarios habilitados</div>', unsafe_allow_html=True)
        st.markdown('<div class="creator-seal">RootMine v4.2.5 Cloud · Creado por <b>Rodrigo Fernández</b></div>', unsafe_allow_html=True)
        st.caption("🔒 La sesión no se comparte mediante la URL. Cada usuario debe iniciar sesión con su propia cuenta.")

def mostrar_menu() -> str:
    usuario = st.session_state.usuario_actual or {}
    with st.sidebar:
        marca_compacta()
        st.caption("GearBot · Asistente de análisis inteligente")
        st.divider()
        st.markdown(f"**Hola, {usuario.get('nombre', st.session_state.usuario).split()[0]}**")
        st.caption(f"{etiqueta_rol(usuario.get('rol',''))} · {usuario.get('area','')}")
        if usuario.get("centro"):
            st.caption(f"Centro {usuario.get('centro')} · {usuario.get('planta','')}")

        if st.button("🚪 Cerrar sesión", key="logout_top", use_container_width=True, type="primary"):
            cerrar_sesion_rootmine()
            st.rerun()

        mostrar_campana(usuario)

        opciones = ["🏠 Dashboard", "📝 RootMine · Nuevo ADF", "✅ Validaciones", "📋 Planes de acción", "📚 Historial", "📊 Indicadores", "🧠 Base de conocimiento"]
        if es_admin_rootmine(usuario):
            opciones.append("👥 Administración de cuentas")
        opciones.append("ℹ️ Acerca de")
        if st.session_state.pagina not in opciones:
            st.session_state.pagina = opciones[0]
        pagina = st.radio("Navegación", opciones, index=opciones.index(st.session_state.pagina), label_visibility="collapsed")
        st.session_state.pagina = pagina

        st.divider()
        configuracion = obtener_configuracion()
        if configuracion.api_key:
            st.success(f"IA centralizada · {configuracion.modelo}")
        else:
            st.error("Falta GEMINI_API_KEY central")
        st.caption(f"💾 Datos: {descripcion_backend()}")
        st.caption("🔔 Notificaciones internas activas")
        st.caption("✉️ Correo externo desactivado en v4.1")

        st.markdown('<div class="sidebar-credit">NeuralMant Suite · RootMine v4.2.5 Cloud<br>© 2026 Rodrigo Fernández</div>', unsafe_allow_html=True)
        return pagina


def main() -> None:
    cargar_estilos()
    preparar_backend()
    inicializar_sesion()
    restaurar_sesion_persistente()
    if not st.session_state.usuario_actual:
        mostrar_identificacion()
        return

    restaurar_contexto_navegacion()
    pagina = mostrar_menu()
    _persistir_contexto_navegacion(pagina)
    barra_inicio(pagina)
    if pagina == "🏠 Dashboard": mostrar_inicio()
    elif pagina == "📝 RootMine · Nuevo ADF": mostrar_nuevo_adf()
    elif pagina == "✅ Validaciones": mostrar_validaciones()
    elif pagina == "📋 Planes de acción": mostrar_planes_accion()
    elif pagina == "📚 Historial": mostrar_historial()
    elif pagina == "📊 Indicadores": mostrar_indicadores()
    elif pagina == "🧠 Base de conocimiento": mostrar_base_conocimiento()
    elif pagina == "👥 Administración de cuentas": mostrar_administracion()
    else: mostrar_acerca()


if __name__ == "__main__":
    main()
