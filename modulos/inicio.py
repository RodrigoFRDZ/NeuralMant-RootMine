import json
from collections import Counter

import streamlit as st

from database.repositorio_adf import listar_adf, listar_pendientes_para, listar_requiere_correccion_para
from modulos.nuevo_adf import cargar_adf_para_correccion


ADMIN_CORREOS = {"rfernandezc@agrosuper.com"}

def _es_admin_rootmine(usuario: dict) -> bool:
    correo = (usuario.get("correo") or usuario.get("email") or "").strip().lower()
    nombre = (usuario.get("nombre") or "").strip().lower()
    rol = (usuario.get("rol") or "").strip().lower()
    return correo in ADMIN_CORREOS or ("rodrigo" in nombre and "fern" in nombre and rol == "ingeniero")


def _json(texto: str, defecto):
    try:
        return json.loads(texto or "")
    except (json.JSONDecodeError, TypeError):
        return defecto


def _causa_resumen(registro) -> str:
    conclusion = (registro.conclusion or "").strip()
    if conclusion:
        return conclusion[:70] + ("…" if len(conclusion) > 70 else "")
    efecto = (registro.efecto or "").strip()
    return efecto[:70] + ("…" if len(efecto) > 70 else "") if efecto else "Pendiente de conclusión"


def mostrar_inicio() -> None:
    primer_nombre = st.session_state.usuario.split()[0]
    registros = listar_adf()
    total = len(registros)
    equipos = len({getattr(r, "numero_equipo", "") or r.equipo for r in registros if getattr(r, "numero_equipo", "") or r.equipo})
    areas = len({r.area for r in registros if r.area})
    con_ia = sum(bool(r.analisis_ia) for r in registros)
    acciones = sum(len(_json(r.plan_prevencion, [])) for r in registros)
    usuario_actual = st.session_state.get("usuario_actual") or {}
    rol_actual = usuario_actual.get("rol", "").lower()
    pendientes_usuario = listar_pendientes_para(usuario_actual.get("correo", ""), rol_actual, usuario_actual.get("centro", "")) if rol_actual in {"supervisor", "jefe", "ingeniero", "subgerente"} else []

    st.markdown(
        f'''<div class="suite-hero">
            <div><div class="eyebrow">NEURALMANT SUITE · ROOTMINE</div>
            <h1>Hola, {primer_nombre}. <span>¿Qué falla analizamos hoy?</span></h1>
            <p>GearBot está listo para acompañarte desde el fenómeno hasta el plan de prevención.</p></div>
            <div class="suite-badge">RCA + IA</div>
        </div>''',
        unsafe_allow_html=True,
    )

    cbot, ctext = st.columns([0.72, 3.3], gap="medium", vertical_alignment="center")
    with cbot:
        st.image("assets/gearbot_small.png", use_container_width=True)
    with ctext:
        st.markdown(
            '''<div class="gearbot-speech"><div class="speech-title">👋 Soy GearBot</div>
            <div>Estoy listo para ayudarte a identificar el fenómeno, ordenar las causas, profundizar con los 5 Porqués y preparar un informe técnico editable.</div></div>''',
            unsafe_allow_html=True,
        )

    st.markdown("### Panel general")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("ADF realizados", total)
    m2.metric("Equipos analizados", equipos)
    m3.metric("Áreas cubiertas", areas)
    if rol_actual in {"supervisor", "jefe"}:
        m4.metric("Mis aprobaciones", len(pendientes_usuario))
    elif rol_actual == "ingeniero":
        m4.metric("Pendientes planta", len(pendientes_usuario))
    elif rol_actual == "subgerente":
        m4.metric("Pendientes globales", len(pendientes_usuario))
    else:
        m4.metric("Análisis con IA", con_ia)
    m5.metric("Acciones registradas", acciones)

    if rol_actual == "ingeniero" and pendientes_usuario:
        st.info(f"⚙️ Hay {len(pendientes_usuario)} ADF pendientes en la planta. Puedes revisarlos desde Validaciones y actuar como reemplazo solo cuando corresponda.")
    elif rol_actual == "subgerente" and pendientes_usuario:
        st.info(f"👁️ Seguimiento global: actualmente hay {len(pendientes_usuario)} ADF pendientes de validación.")
    elif rol_actual in {"supervisor", "jefe"} and pendientes_usuario:
        st.warning(f"✅ Tienes {len(pendientes_usuario)} ADF pendientes de tu validación.")

    if pendientes_usuario and rol_actual in {"supervisor", "jefe", "ingeniero"}:
        if st.button("✅ Ir a revisar y liberar ADF pendientes", type="primary", use_container_width=True, key="dash_validaciones"):
            st.session_state.pagina = "✅ Validaciones"
            st.rerun()

    # Bandeja personal: todo rechazo vuelve al creador para corrección y reenvío.
    correcciones = listar_requiere_correccion_para(usuario_actual.get("correo", ""))
    if correcciones:
        st.markdown("### 🛠️ ADF devueltos para corrección")
        st.warning(f"Tienes {len(correcciones)} ADF rechazado(s) que requieren ajustes antes de reenviarlos a validación.")
        for adf in correcciones:
            with st.container(border=True):
                cinfo, caccion = st.columns([4, 1.25], vertical_alignment="center")
                with cinfo:
                    st.markdown(f"**ADF #{adf.id} · {adf.equipo}**")
                    st.caption(f"{adf.area} · {adf.etapa}")
                    st.write(f"**Observación del validador:** {adf.comentario_validacion or 'Sin comentario registrado'}")
                with caccion:
                    if st.button("✏️ Corregir ADF", key=f"corregir_dash_{adf.id}", type="primary", use_container_width=True):
                        if cargar_adf_para_correccion(adf.id):
                            st.rerun()
                        else:
                            st.error("No fue posible abrir este ADF para corrección.")

    st.markdown("### Accesos rápidos")
    a1, a2, a3, a4, a5 = st.columns(5)
    with a1:
        st.markdown('<div class="action-card blue"><div class="action-icon">📝</div><h3>Nuevo ADF</h3><p>Inicia un análisis guiado de causa raíz.</p></div>', unsafe_allow_html=True)
        if st.button("Comenzar →", type="primary", use_container_width=True, key="dash_nuevo"):
            st.session_state.pagina = "📝 RootMine · Nuevo ADF"
            st.session_state.pop("nuevo_adf", None)
            st.rerun()
    with a2:
        st.markdown('<div class="action-card amber"><div class="action-icon">📚</div><h3>Historial</h3><p>Revisa análisis y conclusiones anteriores.</p></div>', unsafe_allow_html=True)
        if st.button("Ver historial →", use_container_width=True, key="dash_hist"):
            st.session_state.pagina = "📚 Historial"
            st.rerun()
    with a3:
        st.markdown('<div class="action-card green"><div class="action-icon">📊</div><h3>Indicadores</h3><p>Visualiza métricas del conocimiento generado.</p></div>', unsafe_allow_html=True)
        if st.button("Ver indicadores →", use_container_width=True, key="dash_ind"):
            st.session_state.pagina = "📊 Indicadores"
            st.rerun()
    with a4:
        st.markdown('<div class="action-card amber"><div class="action-icon">📋</div><h3>Planes</h3><p>Gestiona vencimientos, respaldos y cierre de acciones.</p></div>', unsafe_allow_html=True)
        if st.button("Gestionar →", use_container_width=True, key="dash_planes"):
            st.session_state.pagina = "📋 Planes de acción"
            st.rerun()
    with a5:
        st.markdown('<div class="action-card purple"><div class="action-icon">🧠</div><h3>Conocimiento</h3><p>Busca fallas, causas y planes ya documentados.</p></div>', unsafe_allow_html=True)
        if st.button("Explorar →", use_container_width=True, key="dash_bc"):
            st.session_state.pagina = "🧠 Base de conocimiento"
            st.rerun()

    # Acceso exclusivo del administrador RootMine.
    if _es_admin_rootmine(usuario_actual):
        st.markdown("#### ⚙️ Administración")
        adm_col, _ = st.columns([1.05, 3.95])
        with adm_col:
            st.markdown(
                '<div class="action-card admin"><div class="action-icon">👥</div>'
                '<h3>Administración</h3>'
                '<p>Crea, edita y elimina cuentas; gestiona roles y restablece llaves de acceso.</p></div>',
                unsafe_allow_html=True,
            )
            if st.button("Administrar cuentas →", type="primary", use_container_width=True, key="dash_admin"):
                st.session_state.pagina = "👥 Administración de cuentas"
                st.rerun()

    left, right = st.columns([1.35, 1], gap="large")
    with left:
        st.markdown("### Análisis recientes")
        if not registros:
            st.info("Aún no existen análisis registrados.")
        else:
            for adf in registros[:5]:
                estado = adf.estado or "Borrador"
                st.markdown(
                    f'''<div class="recent-row"><div class="recent-icon">📄</div>
                    <div class="recent-copy"><b>ADF #{adf.id} · {adf.equipo}</b><span>{((getattr(adf, "centro", "") or "") + (" - " + getattr(adf, "planta", "") if getattr(adf, "planta", "") else "")) or "Centro no registrado"} · {adf.area} · N° {getattr(adf, "numero_equipo", "") or "s/i"} · {_causa_resumen(adf)}</span></div>
                    <div class="recent-meta"><span>{adf.fecha_actualizacion:%d/%m/%Y}</span><em>{estado}</em></div></div>''',
                    unsafe_allow_html=True,
                )
    with right:
        st.markdown("### Módulos NeuralMant")
        st.markdown('''<div class="module-stack">
          <div class="module-item active"><b>RootMine</b><span>Análisis inteligente de causa raíz</span></div>
          <div class="module-item"><b>Predict</b><span>Mantenimiento predictivo · Próximamente</span></div>
          <div class="module-item"><b>StockMind</b><span>Optimización de repuestos · Próximamente</span></div>
          <div class="module-item"><b>Planner</b><span>Estrategias y planes · Próximamente</span></div>
        </div>''', unsafe_allow_html=True)

    st.info("Las sugerencias de GearBot son una guía de investigación. La validación final siempre corresponde al equipo técnico.")
