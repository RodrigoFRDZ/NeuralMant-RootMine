import re
import streamlit as st
from database.materiales import listar, puede_actuar
from modulos.navegacion_materiales import abrir_material

from database.notificaciones import listar_notificaciones, marcar_leida, marcar_todas_leidas


@st.cache_data(ttl=20, show_spinner=False)
def _notificaciones_cache(email: str) -> list[dict]:
    items = listar_notificaciones(email, limite=10)
    return [
        {
            "id": n.id,
            "titulo": n.titulo,
            "mensaje": n.mensaje,
            "fecha": n.fecha,
            "leida": bool(n.leida),
            "tipo": n.tipo,
        }
        for n in items
    ]

def folio_material(notificacion):
    tipo = notificacion.get("tipo", "") or ""
    if tipo.startswith("materiales:"):
        valor = tipo.split(":",1)[1]
        return int(valor) if valor.isdigit() and int(valor)>0 else None
    if tipo == "materiales":
        match = re.search(r"Materiales #(\d+)", notificacion.get("titulo", ""))
        return int(match.group(1)) if match else None
    return None


@st.fragment(run_every="15s")
def mostrar_aviso_materiales(usuario):
    correo = usuario.get("correo", "")
    if not correo:
        return
    pendientes = [r for r in listar(correo) if puede_actuar(r, usuario)]
    if not pendientes:
        return
    with st.container(border=True):
        st.info(f"🔔 Tienes {len(pendientes)} solicitudes de materiales para revisar.")
        for r in pendientes[:3]:
            st.link_button(f"Abrir solicitud #{r['id']} · {r['material']} · {r['estado']}",
                           url=f"?solicitud_material={r['id']}", use_container_width=True)
        if st.button("Ir a mis aprobaciones de materiales", key="mat_ir_aprobaciones", use_container_width=True):
            abrir_material(pendientes[0]["id"])
            st.rerun(scope="app")


def mostrar_campana(usuario: dict) -> None:
    email = usuario.get("correo", "")
    notificaciones = _notificaciones_cache(email)
    no_leidas = [n for n in notificaciones if not n["leida"]]
    etiqueta = f"🔔 Notificaciones ({len(no_leidas)})" if no_leidas else "🔔 Notificaciones"
    with st.expander(etiqueta):
        if not notificaciones:
            st.caption("No tienes notificaciones internas.")
            return
        for n in notificaciones:
            marca = "🔵" if not n["leida"] else "⚪"
            st.markdown(f"{marca} **{n["titulo"]}**")
            st.caption(f"{n["fecha"]:%d-%m-%Y %H:%M} · {n["mensaje"]}")
            folio = folio_material(n)
            if folio:
                st.link_button("Abrir solicitud de materiales", url=f"?solicitud_material={folio}", use_container_width=True)
            if not n["leida"] and st.button("Marcar leída", key=f"notif_read_{n["id"]}", use_container_width=True):
                marcar_leida(n["id"]); _notificaciones_cache.clear(); st.rerun()
        if no_leidas and st.button("Marcar todas como leídas", key="notif_read_all", use_container_width=True):
            marcar_todas_leidas(email); _notificaciones_cache.clear(); st.rerun()
