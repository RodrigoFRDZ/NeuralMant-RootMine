import json
from collections import Counter
import streamlit as st
from database.repositorio_adf import listar_adf


def mostrar_indicadores() -> None:
    registros = listar_adf()
    st.markdown('<div class="hero"><div class="eyebrow">NEURALMANT ANALYTICS</div><h1>Indicadores RootMine</h1><p>Visión consolidada de los análisis, equipos y acciones preventivas.</p></div>', unsafe_allow_html=True)
    acciones = 0
    for r in registros:
        try:
            acciones += len(json.loads(r.plan_prevencion or "[]"))
        except Exception:
            pass
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("ADF totales", len(registros))
    c2.metric("Áreas cubiertas", len({r.area for r in registros}) if registros else 0)
    c3.metric("Equipos analizados", len({r.equipo for r in registros}) if registros else 0)
    c4.metric("Con conclusión", sum(bool(r.conclusion) for r in registros))
    c5.metric("Acciones", acciones)
    if not registros:
        st.info("Aún no hay datos suficientes para construir indicadores.")
        return

    areas = Counter(r.area for r in registros)
    equipos = Counter(r.equipo for r in registros)
    estados = Counter((r.estado or "Borrador") for r in registros)
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("ADF por área")
        st.bar_chart(dict(areas), horizontal=True)
    with col2:
        st.subheader("Equipos con más análisis")
        st.bar_chart(dict(equipos.most_common(10)), horizontal=True)
    st.subheader("Estado de los análisis")
    st.bar_chart(dict(estados))
