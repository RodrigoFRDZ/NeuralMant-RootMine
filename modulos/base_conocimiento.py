import json
import streamlit as st
from database.repositorio_adf import listar_adf


def _json(texto: str, defecto):
    try:
        return json.loads(texto or "")
    except (json.JSONDecodeError, TypeError):
        return defecto


def mostrar_base_conocimiento() -> None:
    registros = listar_adf()
    st.markdown(
        '''<div class="hero"><div class="eyebrow">CONOCIMIENTO NEURALMANT</div>
        <h1>Base de conocimiento <span>RootMine</span></h1>
        <p>Consulta aprendizajes, causas raíz y acciones provenientes de análisis anteriores.</p></div>''',
        unsafe_allow_html=True,
    )
    if not registros:
        st.info("Todavía no existen análisis guardados para consultar.")
        return

    consulta = st.text_input(
        "Buscar en los ADF",
        placeholder="Ejemplo: lubricación, rodamiento, humedad, sensor…",
    ).strip().lower()

    coincidencias = []
    for adf in registros:
        texto = " ".join([
            adf.area or "", adf.equipo or "", adf.relato_original or "",
            adf.efecto or "", adf.conclusion or "", adf.plan_prevencion or "",
        ]).lower()
        if not consulta or consulta in texto:
            coincidencias.append(adf)

    st.caption(f"{len(coincidencias)} análisis encontrados")
    for adf in coincidencias:
        plan = _json(adf.plan_prevencion, [])
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f"### ADF #{adf.id} · {adf.equipo}")
                st.caption(f"{adf.area} · {adf.fecha_actualizacion:%d/%m/%Y}")
                if adf.efecto:
                    st.markdown(f"**Fenómeno:** {adf.efecto}")
                if adf.conclusion:
                    st.markdown(f"**Conclusión:** {adf.conclusion}")
            with c2:
                st.metric("Acciones", len(plan))
            if plan:
                with st.expander("Ver planes de prevención"):
                    for accion in plan:
                        if isinstance(accion, dict):
                            st.write(f"• {accion.get('accion', 'Acción sin nombre')}")
                        else:
                            st.write(f"• {accion}")
