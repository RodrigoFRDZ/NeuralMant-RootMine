import streamlit as st

from database.notificaciones import listar_notificaciones, marcar_leida, marcar_todas_leidas


def mostrar_campana(usuario: dict) -> None:
    email = usuario.get("correo", "")
    notificaciones = listar_notificaciones(email, limite=10)
    no_leidas = [n for n in notificaciones if not n.leida]
    etiqueta = f"🔔 Notificaciones ({len(no_leidas)})" if no_leidas else "🔔 Notificaciones"
    with st.expander(etiqueta):
        if not notificaciones:
            st.caption("No tienes notificaciones internas.")
            return
        for n in notificaciones:
            marca = "🔵" if not n.leida else "⚪"
            st.markdown(f"{marca} **{n.titulo}**")
            st.caption(f"{n.fecha:%d-%m-%Y %H:%M} · {n.mensaje}")
            if not n.leida and st.button("Marcar leída", key=f"notif_read_{n.id}", use_container_width=True):
                marcar_leida(n.id)
                st.rerun()
        if no_leidas and st.button("Marcar todas como leídas", key="notif_read_all", use_container_width=True):
            marcar_todas_leidas(email)
            st.rerun()
