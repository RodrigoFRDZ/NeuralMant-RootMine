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
    from modulos.gestion_adf_resumen import mostrar_resumen
    with st.expander("📊 Resumen de estados y agrupación de fallas"):
        mostrar_resumen()
    if not registros:
        st.info("Todavía no existen análisis guardados para consultar.")
        return

    consulta = st.text_input(
        "Buscar en los ADF",
        placeholder="Centro, N° de equipo, equipo, causa, fenómeno, acción…",
    ).strip().lower()

    coincidencias = []
    for adf in registros:
        texto = " ".join([
            getattr(adf, "centro", "") or "", getattr(adf, "planta", "") or "", getattr(adf, "numero_equipo", "") or "",
            adf.area or "", adf.equipo or "", adf.relato_original or "",
            adf.efecto or "", adf.conclusion or "", adf.plan_prevencion or "",
        ]).lower()
        if not consulta or consulta in texto:
            coincidencias.append(adf)

    st.caption(f"{len(coincidencias)} análisis encontrados")
    if coincidencias:
        st.download_button("📥 Exportar resultados filtrados a Excel", _exportar_conocimiento(coincidencias), file_name="Conocimiento_RootMine.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    for adf in coincidencias:
        plan = _json(adf.plan_prevencion, [])
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f"### ADF #{adf.id} · {adf.equipo}")
                centro_txt = ((getattr(adf, "centro", "") or "") + (" - " + getattr(adf, "planta", "") if getattr(adf, "planta", "") else "")) or "Centro no registrado"
                st.caption(f"{centro_txt} · {adf.area} · N° equipo: {getattr(adf, 'numero_equipo', '') or 'No registrado'} · {adf.fecha_actualizacion:%d/%m/%Y}")
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


def _exportar_conocimiento(registros):
    """Exportación estructurada sin modificar ADF originales."""
    import io
    import pandas as pd
    filas=[]
    acciones=[]
    for a in registros:
        filas.append({'ADF':a.id,'Centro':getattr(a,'centro',''),'Planta':getattr(a,'planta',''),
                      'Área':a.area,'Equipo':a.equipo,'N° equipo':getattr(a,'numero_equipo',''),
                      'Estado':getattr(a,'estado',''),'Fenómeno':a.efecto,'Relato':a.relato_original,
                      'Conclusión':a.conclusion,'Fecha actualización':str(a.fecha_actualizacion)})
        for p in _json(a.plan_prevencion,[]):
            acciones.append({'ADF':a.id,'Equipo':a.equipo,'Acción':p.get('accion','') if isinstance(p,dict) else str(p),
                             'Detalle':json.dumps(p,ensure_ascii=False) if isinstance(p,dict) else ''})
    b=io.BytesIO()
    with pd.ExcelWriter(b,engine='openpyxl') as w:
        pd.DataFrame(filas).to_excel(w,sheet_name='ADF',index=False)
        pd.DataFrame(acciones,columns=['ADF','Equipo','Acción','Detalle']).to_excel(w,sheet_name='Acciones',index=False)
    return b.getvalue()
