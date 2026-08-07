import json
import streamlit as st
from database.repositorio_adf import listar_adf


def _json(texto: str, defecto):
    try:
        return json.loads(texto or "")
    except (json.JSONDecodeError, TypeError):
        return defecto


def mostrar_historial() -> None:
    st.markdown('''<div class="hero"><div class="eyebrow">ROOTMINE · REGISTRO</div><h1>Historial de análisis</h1><p>Revisa ADF guardados, conclusiones y planes de prevención.</p></div>''', unsafe_allow_html=True)
    registros = listar_adf()
    if not registros:
        st.info("Todavía no existen ADF guardados.")
        return

    filtro, estado_col = st.columns([3, 1])
    with filtro:
        busqueda = st.text_input("Buscar", placeholder="Equipo, área, fenómeno o conclusión").strip().lower()
    with estado_col:
        estados = ["Todos"] + sorted({r.estado or "Borrador" for r in registros})
        estado = st.selectbox("Estado", estados)

    encontrados = 0
    for adf in registros:
        contenido = " ".join([adf.equipo or "", adf.area or "", adf.efecto or "", adf.conclusion or ""]).lower()
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
                st.caption(f"{adf.area} · Creado por {adf.creado_por}")
                st.write(f"**Fenómeno:** {adf.efecto or 'Pendiente'}")
            with c3:
                st.markdown(f'<div class="status-pill">{adf.estado or "Borrador"}</div>', unsafe_allow_html=True)
                st.caption(adf.fecha_actualizacion.strftime("%d/%m/%Y"))
            with st.expander("Ver detalle completo"):
                st.write(f"**Relato original:** {adf.relato_original}")
                if adf.conclusion:
                    st.subheader("Conclusión")
                    st.write(adf.conclusion)
                plan = _json(adf.plan_prevencion, [])
                if plan:
                    st.subheader("Planes de prevención")
                    for accion in plan:
                        st.write(f"• {accion.get('accion', accion) if isinstance(accion, dict) else accion}")
    st.caption(f"{encontrados} análisis mostrados")
