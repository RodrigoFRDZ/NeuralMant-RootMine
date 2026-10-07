import json
from collections import Counter

import streamlit as st

from database.rendimiento import borradores_livianos, correcciones_livianas, contar_pendientes, recientes_livianos
from database.repositorio_adf import eliminar_borrador_adf
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


def _modulos_inicio(usuario):
    st.markdown("### Elige tu módulo")
    st.markdown("""<style>
    .inicio-module {background:#FFF6E6;color:#003087;padding:20px;border-radius:12px;
        min-height:170px;box-sizing:border-box;font-family:'Poppins','Montserrat',sans-serif;}
    .inicio-module h3 {color:#003087;margin:0 0 12px;font-size:1.15rem;line-height:1.4;min-height:48px;}
    .inicio-module p {color:#003087;margin:0;font-size:.9rem;line-height:1.5;}
    @media(max-width:900px) {.inicio-module {min-height:190px;}}
    </style>""", unsafe_allow_html=True)
    modulos = [
        ("📝 RootMine · Análisis de fallas", "Crea o continúa un ADF con el apoyo de GearBot.", "📝 RootMine · Nuevo ADF", "nuevo"),
        ("📦 Gestión de materiales", "Stock de seguridad, incorporación al MRP y guía de criticidad.", "📦 Gestión de Materiales", "materiales"),
        ("📋 Planes de acción", "Revisa compromisos, vencimientos y cierre de acciones.", "📋 Planes de acción", "planes"),
        ("📚 Historial", "Consulta los análisis y las conclusiones de tu equipo.", "📚 Historial", "hist"),
        ("📊 Indicadores", "Revisa el avance y los resultados de los análisis.", "📊 Indicadores", "ind"),
        ("🧠 Base de conocimiento", "Busca fallas, causas y soluciones documentadas.", "🧠 Base de conocimiento", "bc"),
        ("✅ Validaciones ADF", "Revisa análisis y las aprobaciones disponibles para tu cuenta.", "✅ Validaciones", "validaciones"),
    ]
    if usuario.get("es_admin") or usuario.get("rol") in ("jefe", "ingeniero", "analizador_materiales", "subgerente"):
        modulos.append(("✅ Aprobaciones de materiales", "Accede directamente a tus solicitudes pendientes de revisión.", "✅ Aprobaciones de materiales", "aprobaciones_materiales"))
    if usuario.get("es_admin"):
        modulos.append(("👥 Administración", "Gestiona cuentas, roles y accesos de los usuarios.", "👥 Administración de cuentas", "admin"))
    for inicio in range(0, len(modulos), 3):
        columnas = st.columns(3)
        for col, (titulo, descripcion, pagina, clave) in zip(columnas, modulos[inicio:inicio+3]):
            with col:
                st.markdown(f'<div class="inicio-module"><h3>{titulo}</h3><p>{descripcion}</p></div>', unsafe_allow_html=True)
                if st.button("Abrir módulo →", key="dash_"+clave, use_container_width=True):
                    st.session_state.pagina = pagina
                    if clave == "materiales":
                        st.session_state["mat_vista"] = None
                    if clave == "nuevo":
                        st.session_state.pop("nuevo_adf", None)
                    st.rerun()


def mostrar_inicio() -> None:
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
            <div><div class="eyebrow">NEURALMANT SUITE</div>
            <h1><span>¿En qué trabajaremos hoy?</span></h1>
            <p>Elige un módulo para comenzar o continuar tu trabajo.</p></div>
            <div class="suite-badge">TU ESPACIO DE TRABAJO</div>
        </div>''',
        unsafe_allow_html=True,
    )

    cbot, ctext = st.columns([0.72, 3.3], gap="medium", vertical_alignment="center")
    with cbot:
        st.image("assets/gearbot_small.png", use_container_width=True)
    with ctext:
        st.markdown(
            '''<div class="gearbot-speech"><div class="speech-title">👋 Soy GearBot</div>
            <div>Estoy listo para ayudarte con lo que trabajaremos hoy: analizar fallas, justificar materiales y orientar su criticidad. También puedes revisar aprobaciones, planes de acción y el conocimiento de tu equipo.</div></div>''',
            unsafe_allow_html=True,
        )

    _modulos_inicio(usuario_actual)

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
                    if st.session_state.get("confirmar_eliminar_borrador") == adf.id:
                        st.warning("¿Eliminar este borrador definitivamente?")
                        if st.button("Sí, eliminar", key=f"confirm_del_borrador_{adf.id}", use_container_width=True):
                            try:
                                if eliminar_borrador_adf(adf.id, usuario_actual.get("correo", "")):
                                    st.session_state.pop("confirmar_eliminar_borrador", None)
                                    st.success("Borrador eliminado.")
                                    st.rerun()
                            except Exception as exc:
                                st.error(str(exc))
                        if st.button("Cancelar", key=f"cancel_del_borrador_{adf.id}", use_container_width=True):
                            st.session_state.pop("confirmar_eliminar_borrador", None)
                            st.rerun()
                    else:
                        if st.button("▶️ Continuar análisis", key=f"continuar_borrador_{adf.id}", type="primary", use_container_width=True):
                            if cargar_borrador_para_continuar(adf.id):
                                st.rerun()
                            else:
                                st.error("No fue posible abrir este borrador.")
                        if st.button("🗑️ Eliminar borrador", key=f"del_borrador_{adf.id}", use_container_width=True):
                            st.session_state["confirmar_eliminar_borrador"] = adf.id
                            st.rerun()

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

    # Acceso exclusivo del administrador RootMine.
    if _es_admin_rootmine(usuario_actual):
        cap_titulo, cap_actualizar = st.columns([4, 1], vertical_alignment="center")
        with cap_titulo:
            st.markdown("#### 📡 Capacidad NeuralMant")
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
            help="Consultas enviadas por NeuralMant durante los últimos 60 minutos.",
        )
        cap2.metric(
            "GearBot · hoy",
            f"{uso_ia.get('hoy', 0)} / {limite_d if limite_d else '—'}",
            help="Consultas enviadas por NeuralMant durante el día actual (hora de Chile).",
        )

        if almacenamiento.get("limite_bytes", 0):
            usados_mb = mb(almacenamiento.get("usados_bytes", 0))
            libres_mb = mb(almacenamiento.get("disponibles_bytes", 0))
            cap3.metric(
                "Nube Supabase",
                f"{libres_mb:.1f} MB libres",
                delta=f"{usados_mb:.1f} MB usados",
                delta_color="off",
                help="Uso de la base PostgreSQL operacional de NeuralMant.",
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
                "NeuralMant ya está contando las consultas automáticamente."
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

    st.info("Las sugerencias de GearBot son una guía de investigación. La validación final siempre corresponde al equipo técnico.")
