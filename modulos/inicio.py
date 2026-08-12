import json
from collections import Counter

import streamlit as st

from database.rendimiento import borradores_livianos, correcciones_livianas, contar_pendientes, recientes_livianos
from database.metricas_sistema import mb
from modulos.cache_lecturas import dashboard_cache, uso_ia_cache, almacenamiento_cache
from ia.cliente import limites_configurados, obtener_configuracion
from modulos.nuevo_adf import cargar_adf_para_correccion, cargar_borrador_para_continuar



def _es_admin_rootmine(usuario: dict) -> bool:
    return bool(usuario.get("es_admin", False))




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
    resumen = dashboard_cache()
    total = resumen["aprobados"]
    equipos = resumen["equipos"]
    areas = resumen["areas"]
    con_ia = resumen["con_ia"]
    acciones = resumen["acciones"]
    usuario_actual = st.session_state.get("usuario_actual") or {}
    rol_actual = usuario_actual.get("rol", "").lower()
    pendientes_usuario = contar_pendientes(usuario_actual.get("correo", ""), rol_actual, usuario_actual.get("centro", "")) if rol_actual in {"supervisor", "jefe", "ingeniero", "subgerente"} else 0

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
    m1.metric("ADF aprobados", total, help="Solo ADF que completaron Supervisor → Jefatura.")
    m2.metric("Equipos analizados", equipos, help="Equipos con al menos un ADF aprobado.")
    m3.metric("Áreas cubiertas", areas, help="Áreas con al menos un ADF aprobado.")
    if rol_actual in {"supervisor", "jefe"}:
        m4.metric("Mis aprobaciones", pendientes_usuario)
    elif rol_actual == "ingeniero":
        m4.metric("Pendientes planta", pendientes_usuario)
    elif rol_actual == "subgerente":
        m4.metric("Pendientes globales", pendientes_usuario)
    else:
        m4.metric("Análisis con IA", con_ia)
    m5.metric("Acciones registradas", acciones)

    if rol_actual == "ingeniero" and pendientes_usuario:
        st.info(f"⚙️ Hay {pendientes_usuario} ADF pendientes en la planta. Puedes revisarlos desde Validaciones y actuar como reemplazo solo cuando corresponda.")
    elif rol_actual == "subgerente" and pendientes_usuario:
        st.info(f"👁️ Seguimiento global: actualmente hay {pendientes_usuario} ADF pendientes de validación.")
    elif rol_actual in {"supervisor", "jefe"} and pendientes_usuario:
        st.warning(f"✅ Tienes {pendientes_usuario} ADF pendientes de tu validación.")

    if pendientes_usuario and rol_actual in {"supervisor", "jefe", "ingeniero"}:
        if st.button("✅ Ir a revisar y liberar ADF pendientes", type="primary", use_container_width=True, key="dash_validaciones"):
            st.session_state.pagina = "✅ Validaciones"
            st.rerun()

    borradores = borradores_livianos(usuario_actual.get("correo", ""), limite=8)
    if borradores:
        st.markdown("### 📝 ADF en progreso")
        st.info(f"Tienes {len(borradores)} análisis sin finalizar. El avance está guardado en la base de datos.")
        for adf in borradores[:8]:
            with st.container(border=True):
                cinfo, caccion = st.columns([4, 1.25], vertical_alignment="center")
                with cinfo:
                    nombre_equipo = adf.equipo if adf.equipo and adf.equipo != "ADF en progreso" else "Análisis sin título"
                    st.markdown(f"**ADF #{adf.id} · {nombre_equipo}**")
                    st.caption(f"{adf.centro or 's/centro'} · {adf.area or 's/área'} · {adf.etapa}")
                    st.write(f"Última actualización: **{adf.fecha_actualizacion:%d/%m/%Y %H:%M}**")
                with caccion:
                    if st.button("▶️ Continuar análisis", key=f"continuar_borrador_{adf.id}", type="primary", use_container_width=True):
                        if cargar_borrador_para_continuar(adf.id):
                            st.rerun()
                        else:
                            st.error("No fue posible abrir este borrador.")

    # Bandeja del creador: llegan rechazos del Supervisor o devoluciones derivadas por el Supervisor tras una observación de Jefatura.
    correcciones = correcciones_livianas(usuario_actual.get("correo", ""), limite=12)
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
        cap_titulo, cap_actualizar = st.columns([4, 1], vertical_alignment="center")
        with cap_titulo:
            st.markdown("#### 📡 Capacidad RootMine")
        with cap_actualizar:
            if st.button("↻ Actualizar", key="refresh_capacidad", use_container_width=True):
                dashboard_cache.clear(); uso_ia_cache.clear(); almacenamiento_cache.clear(); st.rerun()
        uso_ia = uso_ia_cache()
        limites = limites_configurados()
        almacenamiento = almacenamiento_cache()
        modelo_ia = obtener_configuracion().modelo

        cap1, cap2, cap3 = st.columns(3)
        limite_h = limites.get("hora", 0)
        limite_d = limites.get("dia", 0)

        cap1.metric(
            "GearBot · última hora",
            f"{uso_ia.get('ultima_hora', 0)} / {limite_h if limite_h else '—'}",
            help="Consultas enviadas por RootMine durante los últimos 60 minutos.",
        )
        cap2.metric(
            "GearBot · hoy",
            f"{uso_ia.get('hoy', 0)} / {limite_d if limite_d else '—'}",
            help="Consultas enviadas por RootMine durante el día actual (hora de Chile).",
        )

        if almacenamiento.get("limite_bytes", 0):
            usados_mb = mb(almacenamiento.get("usados_bytes", 0))
            libres_mb = mb(almacenamiento.get("disponibles_bytes", 0))
            cap3.metric(
                "Nube Supabase",
                f"{libres_mb:.1f} MB libres",
                delta=f"{usados_mb:.1f} MB usados",
                delta_color="off",
                help="Uso de la base PostgreSQL operacional de RootMine.",
            )
            st.progress(min(1.0, almacenamiento.get("porcentaje", 0) / 100.0))
            st.caption(
                f"☁️ Base de datos: {usados_mb:.1f} MB usados de 500 MB · "
                f"{libres_mb:.1f} MB disponibles. Modelo GearBot: {modelo_ia}."
            )
        else:
            cap3.metric("Base de datos", almacenamiento.get("backend", "No disponible"))

        if not limite_h or not limite_d:
            st.info(
                "Para mostrar el porcentaje exacto de cuota de GearBot, configura "
                "`GEMINI_HOURLY_LIMIT` y `GEMINI_DAILY_LIMIT` en Secrets con los "
                "límites que muestra Google AI Studio para este proyecto/modelo. "
                "RootMine ya está contando las consultas automáticamente."
            )
        elif limite_h or limite_d:
            if limite_h:
                st.progress(min(1.0, uso_ia.get("ultima_hora", 0) / max(1, limite_h)))
            if limite_d:
                st.progress(min(1.0, uso_ia.get("hoy", 0) / max(1, limite_d)))

        if uso_ia.get("rechazos_cuota_hoy", 0):
            st.warning(
                f"GearBot ha registrado {uso_ia['rechazos_cuota_hoy']} intento(s) "
                "rechazados por cuota durante el día."
            )

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
        recientes = recientes_livianos(limite=5)
        st.markdown("### Análisis recientes")
        if not recientes:
            st.info("Aún no existen análisis registrados.")
        else:
            for adf in recientes:
                estado = adf.estado or "Borrador"
                st.markdown(
                    f'''<div class="recent-row"><div class="recent-icon">📄</div>
                    <div class="recent-copy"><b>ADF #{adf.id} · {adf.equipo}</b><span>{((adf.centro or "") + (" - " + adf.planta if adf.planta else "")) or "Centro no registrado"} · {adf.area} · N° {adf.numero_equipo or "s/i"} · {_causa_resumen(adf)}</span></div>
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
