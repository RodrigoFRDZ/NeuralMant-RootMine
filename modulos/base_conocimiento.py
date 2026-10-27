import json
import streamlit as st
from database.repositorio_adf import listar_adf
from modulos.agrupacion_fallas import agrupar_registros, normalizar, sugerir


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
    # Las correcciones se mantienen solo durante la sesión; no alteran ADF históricos.
    reemplazos = st.session_state.setdefault("conocimiento_grupos_revisados", {})
    with st.expander("🧩 Modos de falla agrupados · revisar y desplegar", expanded=True):
        st.caption("Agrupación automática conservadora. Las categorías son sugerencias, no diagnósticos IA. No modifica los ADF originales.")
        grupos = agrupar_registros(coincidencias, reemplazos)
        st.metric("Grupos visibles", len(grupos))
        for grupo, elementos in grupos.items():
            with st.expander(f"{grupo} · {len(elementos)} ADF"):
                for a, original in elementos:
                    st.write(f"ADF #{a.id} · {a.equipo or 'Sin equipo'} · {original or 'Sin descripción'}")
        originales = sorted({str(getattr(a, "efecto", "") or "").strip() for a in coincidencias if getattr(a, "efecto", "")})
        if originales:
            st.markdown("**Corregir agrupación (solo vista actual)**")
            original_sel = st.selectbox("Descripción original", originales, key="conocimiento_original_grupo")
            pred = reemplazos.get(normalizar(original_sel), sugerir(original_sel))
            nuevo = st.text_input("Categoría genérica", value=pred, key="conocimiento_nuevo_grupo")
            if st.button("Aplicar corrección", key="conocimiento_guardar_grupo"):
                if nuevo.strip():
                    reemplazos[normalizar(original_sel)] = nuevo.strip()[:120]
                    st.rerun()
            st.caption("La corrección no persiste al cerrar sesión. Se requiere aprobación y almacenamiento controlado para hacerla permanente.")
    if coincidencias:
        st.download_button("📥 Exportar resultados filtrados a Excel", _exportar_conocimiento(coincidencias, reemplazos), file_name="Conocimiento_RootMine.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
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


def _exportar_conocimiento(registros, reemplazos=None):
    """Exportación estructurada sin modificar ADF originales."""
    import io
    import pandas as pd
    filas=[]
    acciones=[]
    reemplazos = reemplazos or {}
    grupos_export=[]
    for a in registros:
        original = str(getattr(a, "efecto", "") or "")
        grupo = reemplazos.get(normalizar(original)) or sugerir(original)
        grupos_export.append({"ADF": a.id, "Grupo genérico": grupo, "Modo de falla original": original,
                              "Equipo": a.equipo, "Área": a.area})
        filas.append({'ADF':a.id,'Centro':getattr(a,'centro',''),'Planta':getattr(a,'planta',''),
                      'Área':a.area,'Equipo':a.equipo,'N° equipo':getattr(a,'numero_equipo',''),
                      'Estado':getattr(a,'estado',''),'Grupo genérico':grupo,'Fenómeno':a.efecto,'Relato':a.relato_original,
                      'Conclusión':a.conclusion,'Fecha actualización':str(a.fecha_actualizacion)})
        for p in _json(a.plan_prevencion,[]):
            acciones.append({'ADF':a.id,'Equipo':a.equipo,'Acción':p.get('accion','') if isinstance(p,dict) else str(p),
                             'Detalle':json.dumps(p,ensure_ascii=False) if isinstance(p,dict) else ''})
    b=io.BytesIO()
    with pd.ExcelWriter(b,engine='openpyxl') as w:
        pd.DataFrame(grupos_export).to_excel(w,sheet_name='Modos agrupados',index=False)
        pd.DataFrame(filas).to_excel(w,sheet_name='ADF',index=False)
        pd.DataFrame(acciones,columns=['ADF','Equipo','Acción','Detalle']).to_excel(w,sheet_name='Acciones',index=False)
    return b.getvalue()
