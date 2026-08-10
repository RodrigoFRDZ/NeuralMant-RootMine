import base64
import json
import streamlit as st

from database.repositorio_adf import listar_adf
from modulos.nuevo_adf import cargar_adf_para_correccion
from reportes.pdf_adf import generar_pdf_adf


def _json(texto: str, defecto):
    try:
        return json.loads(texto or "")
    except (json.JSONDecodeError, TypeError):
        return defecto


def _pdf_desde_registro(adf) -> bytes:
    """Reconstruye un PDF para registros antiguos que todavía no guardaban el archivo."""
    ishikawa = _json(adf.ishikawa, {})
    cadenas = _json(adf.cadenas_causales, [])
    plan = _json(adf.plan_prevencion, [])
    datos = {
        "titulo": f"INFORME DE ANÁLISIS DE FALLA · ADF #{adf.id}",
        "resumen_ejecutivo": adf.conclusion or adf.efecto or "Análisis registrado en RootMine.",
        "descripcion_evento": adf.relato_original or "",
        "principio_funcionamiento": adf.investigacion_web or "No registrado en esta versión del análisis.",
        "fenomeno_investigado": adf.efecto or "",
        "sintesis_ishikawa": "Análisis causal 6M registrado en RootMine.",
        "conclusion_tecnica": adf.conclusion or "",
        "leccion_aprendida": adf.leccion_aprendida or "",
        "creado_por": adf.creado_por or "",
        "centro": getattr(adf, "centro", "") or "",
        "planta": getattr(adf, "planta", "") or "",
        "area": adf.area or "",
        "numero_equipo": getattr(adf, "numero_equipo", "") or "",
        "equipo": adf.equipo or "",
        "aviso_sap": adf.aviso_sap or "",
        "relato_original": adf.relato_original or "",
        "efecto": adf.efecto or "",
        "ishikawa_validado": ishikawa,
        "cadenas_causales": cadenas,
        "plan_prevencion": plan,
    }
    return generar_pdf_adf(datos)


def mostrar_historial() -> None:
    st.markdown('''<div class="hero"><div class="eyebrow">ROOTMINE · REGISTRO</div><h1>Historial de análisis</h1><p>Revisa ADF guardados, conclusiones, planes de prevención y descarga el informe PDF.</p></div>''', unsafe_allow_html=True)
    registros = listar_adf()
    if not registros:
        st.info("Todavía no existen ADF guardados.")
        return

    filtro, estado_col = st.columns([3, 1])
    with filtro:
        busqueda = st.text_input("Buscar", placeholder="Centro, N° de equipo, equipo, área, fenómeno o conclusión").strip().lower()
    with estado_col:
        estados = ["Todos"] + sorted({r.estado or "Borrador" for r in registros})
        estado = st.selectbox("Estado", estados)

    encontrados = 0
    for adf in registros:
        contenido = " ".join([getattr(adf, "centro", "") or "", getattr(adf, "planta", "") or "", getattr(adf, "numero_equipo", "") or "", adf.equipo or "", adf.area or "", adf.efecto or "", adf.conclusion or ""]).lower()
        if busqueda and busqueda not in contenido:
            continue
        if estado != "Todos" and (adf.estado or "Borrador") != estado:
            continue
        encontrados += 1
        with st.container(border=True):
            c1, c2, c3 = st.columns([0.55, 4.5, 1.35], vertical_alignment="center")
            with c1:
                st.markdown('<div class="history-doc">📄</div>', unsafe_allow_html=True)
            with c2:
                st.markdown(f"### ADF #{adf.id} · {adf.equipo}")
                centro_txt = ((getattr(adf, "centro", "") or "") + (" - " + getattr(adf, "planta", "") if getattr(adf, "planta", "") else "")) or "Centro no registrado"
                st.caption(f"{centro_txt} · {adf.area} · N° equipo: {getattr(adf, 'numero_equipo', '') or 'No registrado'} · Creado por {adf.creado_por}")
                st.write(f"**Fenómeno:** {adf.efecto or 'Pendiente'}")
            with c3:
                st.markdown(f'<div class="status-pill">{adf.estado or "Borrador"}</div>', unsafe_allow_html=True)
                st.caption(adf.fecha_actualizacion.strftime("%d/%m/%Y"))

            detalle, pdf_col = st.columns([2.4, 1], vertical_alignment="center")
            with detalle:
                usuario = st.session_state.get("usuario_actual") or {}
                es_creador = (getattr(adf, "creado_por_email", "") or "").lower().strip() == (usuario.get("correo") or "").lower().strip()
                if es_creador and (adf.estado or "") in {"Rechazado", "Requiere corrección"}:
                    st.warning(f"🛠️ Devuelto para corrección: {adf.comentario_validacion or 'Revisa las observaciones del validador.'}")
                    if st.button("✏️ Corregir y reenviar ADF", key=f"corregir_hist_{adf.id}", type="primary"):
                        if cargar_adf_para_correccion(adf.id):
                            st.rerun()
                        else:
                            st.error("No fue posible abrir este ADF para corrección.")
            with pdf_col:
                try:
                    pdf_bytes = getattr(adf, "pdf_archivo", None) or _pdf_desde_registro(adf)
                    nombre_seguro = "_".join((adf.equipo or "Equipo").split())
                    st.download_button(
                        "📥 Descargar PDF del análisis",
                        data=pdf_bytes,
                        file_name=f"ADF_{adf.id}_{nombre_seguro}.pdf",
                        mime="application/pdf",
                        key=f"pdf_historial_{adf.id}",
                        use_container_width=True,
                    )
                except Exception as error:
                    st.warning(f"No fue posible preparar el PDF: {error}")

            with st.expander("Ver detalle completo"):
                st.write(f"**Relato original:** {adf.relato_original}")
                if adf.conclusion:
                    st.subheader("Conclusión")
                    st.write(adf.conclusion)
                plan = _json(adf.plan_prevencion, [])
                if plan:
                    st.subheader("Planes de prevención")
                    for indice, accion in enumerate(plan, start=1):
                        if not isinstance(accion, dict):
                            st.write(f"• {accion}")
                            continue
                        with st.container(border=True):
                            st.markdown(f"**{indice}. {accion.get('accion','Acción')}**")
                            st.caption(f"Responsable: {accion.get('responsable_sugerido','—')} · Compromiso: {accion.get('fecha_compromiso') or accion.get('plazo_sugerido','—')} · Estado: {accion.get('estado_ejecucion','Pendiente')}")
                            st.write(f"**Evidencia esperada / registrada:** {accion.get('evidencia_de_implementacion','—')}")
                            sap = []
                            if accion.get('noti_sap'): sap.append(f"NOTI {accion.get('noti_sap')}")
                            if accion.get('status_usuario_sap'): sap.append(f"Status {accion.get('status_usuario_sap')}")
                            if accion.get('mov_mercancias'): sap.append(f"MOV {accion.get('mov_mercancias')}")
                            if float(accion.get('gasto_asociado',0) or 0) > 0: sap.append(f"Gasto {accion.get('gasto_asociado')} {accion.get('moneda_gasto','CLP')}")
                            if sap:
                                st.write("**Respaldo SAP:** " + " · ".join(sap))
                            respaldos = accion.get('respaldos') or []
                            if respaldos:
                                st.write("**Respaldos de ejecución:**")
                                cols = st.columns(min(3, len(respaldos)))
                                for ridx, respaldo in enumerate(respaldos):
                                    try:
                                        data = base64.b64decode(respaldo.get('b64',''))
                                        if data:
                                            cols[ridx % len(cols)].image(data, caption=f"{respaldo.get('tipo','Respaldo')} · {respaldo.get('nombre','')}", use_container_width=True)
                                    except Exception:
                                        pass
                            elif accion.get('respaldo_b64'):
                                try:
                                    st.image(base64.b64decode(accion['respaldo_b64']), caption=accion.get('respaldo_nombre','Respaldo de ejecución'), width=650)
                                except Exception:
                                    st.caption("El respaldo de imagen no pudo visualizarse.")
                            if accion.get('revision_ia'):
                                rev = accion['revision_ia']
                                st.info(f"Revisión IA: {rev.get('veredicto','—')} · Confianza {rev.get('confianza','—')}% — {rev.get('resumen','')}")
                                if rev.get('orden_trabajo_detectada') or rev.get('status_usuario_detectado') or rev.get('fecha_fin_extrema_detectada'):
                                    st.write(f"**OT:** {rev.get('orden_trabajo_detectada') or 'No verificable'} · **Status:** {rev.get('status_usuario_detectado') or 'No verificable'} · **Fecha fin extrema:** {rev.get('fecha_fin_extrema_detectada') or 'No verificable'}")
                                if rev.get('encabezado_orden') or rev.get('descripcion_orden'):
                                    st.write(f"**Encabezado / texto OT:** {rev.get('encabezado_orden') or rev.get('descripcion_orden')}")
                                if rev.get('comparacion_antes_despues'):
                                    st.write(f"**Antes vs. después:** {rev.get('comparacion_antes_despues')}")
                                st.write("**Ejecución confirmada por IA:** " + ("Sí" if rev.get('ejecucion_confirmada') else "No"))
    st.caption(f"{encontrados} análisis mostrados")
