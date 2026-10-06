"""Acceso a solicitudes de materiales sin alterar permisos ni aprobar acciones."""
import streamlit as st


def abrir_material(solicitud_id):
    n = int(solicitud_id)
    if n <= 0:
        raise ValueError("Folio inválido.")
    st.session_state["pagina"] = "📦 Gestión de Materiales"
    st.session_state["mat_vista"] = "Seguimiento y aprobaciones"
    st.session_state["mat_solicitud_enlace"] = n


def abrir_material_desde_url():
    valor = st.query_params.get("solicitud_material")
    if valor is None:
        return
    try:
        abrir_material(valor)
    except (TypeError, ValueError):
        st.session_state["mat_flash"] = "El enlace no contiene un folio de materiales válido."
    st.query_params.pop("solicitud_material", None)
