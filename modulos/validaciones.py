import json
import streamlit as st
from modulos.historial import _pdf_desde_registro

from database.repositorio_adf import aplicar_validacion, historial_validaciones, listar_pendientes_para, resolver_devolucion_jefatura


def _detalle_adf(adf) -> None:
    centro_txt = ((adf.centro or "") + (" - " + adf.planta if getattr(adf, "planta", "") else "")) or "—"
    c1, c2, c3, c4 = st.columns(4)
    c1.write(f"**Centro:** {centro_txt}")
    c2.write(f"**Área:** {adf.area}")
    c3.write(f"**N° Equipo:** {adf.numero_equipo or '—'}")
    c4.write(f"**Estado:** {adf.estado}")
    st.write(f"**Equipo:** {adf.equipo}")
    st.write(f"**Fenómeno:** {adf.efecto or '—'}")
    st.write(f"**Conclusión / causa raíz:** {adf.conclusion or '—'}")
    st.write(f"**Creado por:** {adf.creado_por}")
    try:
        plan = json.loads(adf.plan_prevencion or "[]")
    except Exception:
        plan = []
    if plan:
        st.markdown("#### Planes de acción propuestos")
        for i, accion in enumerate(plan, start=1):
            if isinstance(accion, dict):
                st.markdown(f"**{i}. {accion.get('accion','Acción')}**")
                st.caption(
                    f"Objetivo: {accion.get('objetivo','—')} · Responsable: {accion.get('responsable_sugerido','Por definir')} · "
                    f"Plazo: {accion.get('fecha_compromiso') or accion.get('plazo_sugerido','Por definir')}"
                )
                st.write(f"Evidencia esperada: {accion.get('evidencia_de_implementacion','—')}")
            else:
                st.write(f"{i}. {accion}")


def mostrar_validaciones() -> None:
    usuario = st.session_state.get("usuario_actual") or {}
    rol = usuario.get("rol", "").lower()
    st.markdown("# ✅ Validaciones ADF")

    if rol == "subgerente":
        st.caption("Vista global de ADF pendientes. Perfil de seguimiento: sin acciones de aprobación.")
    elif rol == "ingeniero":
        st.caption("Vista transversal. Puedes actuar como reemplazo de Supervisor o Jefe cuando sea necesario.")
    else:
        st.caption("Bandeja de aprobación según tu responsabilidad y área.")

    if rol not in {"supervisor", "jefe", "ingeniero", "subgerente"}:
        st.info("Tu perfil no tiene una bandeja de aprobación. Puedes consultar el estado de tus ADF desde Historial.")
        return

    pendientes = listar_pendientes_para(usuario.get("correo", ""), rol, usuario.get("centro", ""))
    if not pendientes:
        st.success("No hay ADF pendientes para mostrar.")
        return

    st.metric("Pendientes por revisar", len(pendientes))
    st.info("Selecciona **Abrir validación** para revisar el ADF y liberar o rechazar el flujo.")

    for adf in pendientes:
        with st.container(border=True):
            cab1, cab2 = st.columns([4, 1])
            with cab1:
                st.subheader(f"ADF #{adf.id} · {adf.equipo}")
                st.caption(f"{adf.centro or '—'} · {adf.area} · Estado: {adf.estado}")
            with cab2:
                abrir = st.toggle("Abrir validación", key=f"abrir_validacion_{adf.id}")

            if not abrir:
                st.write(f"**Fenómeno:** {(adf.efecto or '—')[:220]}")
                continue

            st.markdown("### Revisión para liberación")
            _detalle_adf(adf)
            try:
                pdf_bytes = getattr(adf, "pdf_archivo", None) or _pdf_desde_registro(adf)
                st.download_button(
                    "📥 Descargar PDF preliminar antes de validar",
                    data=pdf_bytes,
                    file_name=f"ADF_{adf.id}_Revision.pdf",
                    mime="application/pdf",
                    key=f"pdf_validacion_{adf.id}",
                    use_container_width=True,
                )
            except Exception as error:
                st.warning(f"No fue posible preparar el PDF de revisión: {error}")

            if adf.estado == "Pendiente Supervisor":
                responsable = adf.supervisor_nombre or "Sin supervisor configurado · disponible para reemplazo del Ingeniero"
                st.caption(f"Etapa actual: **Supervisor** · Responsable: {responsable}")
            elif adf.estado == "Devuelto por Jefatura":
                responsable = adf.supervisor_nombre or "Supervisor no configurado · disponible para reemplazo del Ingeniero"
                st.warning("↩️ **Devuelto por Jefatura**")
                st.write(f"**Observación de Jefatura:** {adf.comentario_validacion or 'Sin comentario registrado'}")
                st.caption(f"Revisión actual: **Supervisor** · Responsable: {responsable}")
            else:
                responsable = adf.jefe_nombre or "Sin jefe configurado · disponible para reemplazo del Ingeniero"
                st.caption(f"Etapa actual: **Jefe** · Responsable: {responsable}")

            if rol == "subgerente":
                st.info("👁️ El perfil Subgerente puede revisar la trazabilidad y el estado, pero no modifica el flujo de aprobación.")
            elif adf.estado == "Devuelto por Jefatura":
                if rol == "ingeniero":
                    st.info("⚙️ Si intervienes como reemplazo del Supervisor, quedará registrado en la trazabilidad.")
                comentario = st.text_area(
                    "Comentario del Supervisor",
                    key=f"comentario_dev_jef_{adf.id}",
                    placeholder="Indica qué debe corregirse o deja una nota de la revisión realizada.",
                )
                d1, d2 = st.columns(2)
                if d1.button("↩️ DEVOLVER AL CREADOR", key=f"devolver_creador_{adf.id}", use_container_width=True):
                    try:
                        resolver_devolucion_jefatura(adf.id, usuario, "devolver_creador", comentario)
                        st.warning(f"ADF #{adf.id} devuelto al creador para corrección.")
                        st.rerun()
                    except Exception as error:
                        st.error(str(error))
                if d2.button("✅ REENVIAR A JEFATURA", key=f"reenviar_jefe_{adf.id}", type="primary", use_container_width=True):
                    try:
                        resolver_devolucion_jefatura(adf.id, usuario, "reenviar_jefe", comentario)
                        st.success(f"ADF #{adf.id} reenviado a Jefatura.")
                        st.rerun()
                    except Exception as error:
                        st.error(str(error))
            else:
                if rol == "ingeniero":
                    st.info("⚙️ Si intervienes fuera del responsable asignado, quedará registrado como reemplazo extraordinario.")
                comentario = st.text_area(
                    "Comentario de validación",
                    key=f"comentario_validacion_{adf.id}",
                    placeholder="Obligatorio si rechazas. Opcional si apruebas.",
                )
                b1, b2 = st.columns(2)
                if b1.button("✅ APROBAR Y LIBERAR", key=f"aprobar_{adf.id}", type="primary", use_container_width=True):
                    try:
                        actualizado = aplicar_validacion(adf.id, usuario, "aprobar", comentario)
                        st.success(f"ADF #{adf.id} actualizado a {actualizado.estado}.")
                        st.rerun()
                    except Exception as error:
                        st.error(str(error))
                if b2.button("❌ RECHAZAR", key=f"rechazar_{adf.id}", use_container_width=True):
                    try:
                        actualizado = aplicar_validacion(adf.id, usuario, "rechazar", comentario)
                        if actualizado.estado == "Devuelto por Jefatura":
                            st.warning(f"ADF #{adf.id} rechazado por Jefatura y devuelto al Supervisor.")
                        else:
                            st.warning(f"ADF #{adf.id} rechazado y devuelto al creador.")
                        st.rerun()
                    except Exception as error:
                        st.error(str(error))

            with st.expander("Ver trazabilidad de validaciones"):
                historial = historial_validaciones(adf.id)
                if not historial:
                    st.caption("Sin movimientos registrados.")
                for mov in historial:
                    st.write(
                        f"{mov.fecha:%d-%m-%Y %H:%M} · **{mov.etapa} / {mov.accion}** · "
                        f"{mov.usuario_nombre} · {mov.comentario or 'Sin comentario'}"
                    )
