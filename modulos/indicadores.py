import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

import streamlit as st

from database.repositorio_adf import listar_adf


def _json(texto, defecto):
    try:
        return json.loads(texto or "")
    except Exception:
        return defecto


def _fecha(valor):
    try:
        return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date() if valor else None
    except Exception:
        return None


def _estado_accion(a):
    if not isinstance(a, dict):
        return "Pendiente"
    if a.get("estado_ejecucion") in {"Ejecutado", "Ejecutado verificado"}:
        return "Ejecutado"
    f = _fecha(a.get("fecha_compromiso"))
    if not f:
        return "Pendiente"
    if f < date.today():
        return "Atrasado"
    if f <= date.today() + timedelta(days=7):
        return "Por vencer"
    return "Pendiente"


def _pendiente_respaldo(a: dict) -> bool:
    if not isinstance(a, dict):
        return True
    if a.get("estado_ejecucion") == "Ejecutado verificado":
        return False
    rev = a.get("revision_ia") or {}
    if rev.get("ejecucion_confirmada") and rev.get("veredicto") == "Ejecución respaldada":
        return False
    return True


def _ir_a(pagina: str, filtro: str | None = None) -> None:
    st.session_state.pagina = pagina
    if pagina == "📋 Planes de acción":
        st.session_state["filtro_planes_desde_indicadores"] = filtro or "Todos"
    elif pagina == "✅ Validaciones":
        st.session_state["filtro_validaciones_desde_indicadores"] = filtro or "Todos"
    st.rerun()


def _tarjeta(col, icono: str, etiqueta: str, valor: str | int, clase: str, ayuda: str, pagina: str | None = None, filtro: str | None = None):
    with col:
        st.markdown(
            f'''<div class="kpi-card {clase}">
                <div class="kpi-icon">{icono}</div>
                <div class="kpi-label">{etiqueta}</div>
                <div class="kpi-value">{valor}</div>
                <div class="kpi-help">{ayuda}</div>
            </div>''',
            unsafe_allow_html=True,
        )
        if pagina:
            if st.button("Ver detalle →", key=f"kpi_{etiqueta}_{filtro}", use_container_width=True):
                _ir_a(pagina, filtro)


def _grafico_barras_horizontal(datos: dict, titulo: str, sufijo: str = "", max_items: int = 10):
    filas = [
        {"categoria": k, "valor": float(v)}
        for k, v in sorted(datos.items(), key=lambda x: x[1], reverse=True)[:max_items]
        if float(v) > 0
    ]
    st.markdown(f"### {titulo}")
    if not filas:
        st.caption("Aún no hay datos suficientes para este gráfico.")
        return
    spec = {
        "data": {"values": filas},
        "mark": {"type": "bar", "cornerRadiusEnd": 8, "height": 24},
        "encoding": {
            "y": {"field": "categoria", "type": "nominal", "sort": "-x", "axis": {"title": None, "labelColor": "#d8e7f5", "labelLimit": 260}},
            "x": {"field": "valor", "type": "quantitative", "axis": {"title": None, "labelColor": "#91abc2", "gridColor": "#173957"}},
            "color": {"value": "#1592ff"},
            "tooltip": [
                {"field": "categoria", "type": "nominal", "title": "Detalle"},
                {"field": "valor", "type": "quantitative", "title": "Valor", "format": ".1f"},
            ],
        },
        "config": {"background": "transparent", "view": {"stroke": None}, "axis": {"domain": False, "ticks": False}},
        "height": max(180, len(filas) * 38),
    }
    st.vega_lite_chart(spec, use_container_width=True)
    if sufijo:
        st.caption(sufijo)


def _grafico_estado_planes(conteo: Counter):
    st.markdown("### Estado de planes de acción")
    orden = ["Ejecutado", "Por vencer", "Atrasado", "Pendiente"]
    filas = [{"estado": e, "cantidad": int(conteo.get(e, 0))} for e in orden]
    total = sum(x["cantidad"] for x in filas)
    if total == 0:
        st.caption("Aún no hay planes estructurados para seguimiento.")
        return
    spec = {
        "data": {"values": filas},
        "mark": {"type": "arc", "innerRadius": 62, "outerRadius": 105, "padAngle": 0.025, "cornerRadius": 5},
        "encoding": {
            "theta": {"field": "cantidad", "type": "quantitative"},
            "color": {
                "field": "estado",
                "type": "nominal",
                "scale": {"domain": orden, "range": ["#21bf73", "#f5a623", "#ff5b5b", "#4e78a7"]},
                "legend": {"orient": "bottom", "labelColor": "#d8e7f5", "title": None},
            },
            "tooltip": [
                {"field": "estado", "type": "nominal", "title": "Estado"},
                {"field": "cantidad", "type": "quantitative", "title": "Planes"},
            ],
        },
        "config": {"background": "transparent", "view": {"stroke": None}},
        "height": 310,
    }
    st.vega_lite_chart(spec, use_container_width=True)



def _modo_falla(adf) -> str:
    """Usa únicamente información registrada en el ADF."""
    efecto = (getattr(adf, "efecto", "") or "").strip()
    if efecto:
        return efecto
    analisis = _json(getattr(adf, "analisis_ia", ""), {})
    if isinstance(analisis, dict):
        return (
            analisis.get("fenomeno_propuesto")
            or analisis.get("fenomeno")
            or "Modo de falla no registrado"
        )
    return "Modo de falla no registrado"


def _causas_adf(adf) -> list[str]:
    """Extrae causas raíz registradas en los 5 Porqués del ADF."""
    cadenas = _json(getattr(adf, "cadenas_causales", ""), [])
    causas = []
    if isinstance(cadenas, list):
        for cadena in cadenas:
            if not isinstance(cadena, dict):
                continue
            causa = (
                cadena.get("causa_raiz_preliminar")
                or cadena.get("causa_raiz")
                or cadena.get("causa")
                or ""
            )
            causa = str(causa).strip()
            if causa and causa not in causas:
                causas.append(causa)
    if not causas:
        conclusion = (getattr(adf, "conclusion", "") or "").strip()
        if conclusion:
            causas.append(conclusion)
    return causas


def _reporte_modos_csv(registros) -> bytes:
    """Reporte plano, trazable y construido solo con ADF guardados en RootMine."""
    import csv
    import io
    salida = io.StringIO()
    campos = [
        "ADF", "Estado", "Centro", "Area", "Numero_equipo", "Equipo",
        "Modo_falla", "Causas", "Tiempo_perdido_h"
    ]
    writer = csv.DictWriter(salida, fieldnames=campos, delimiter=";")
    writer.writeheader()
    for r in registros:
        writer.writerow({
            "ADF": getattr(r, "id", ""),
            "Estado": getattr(r, "estado", "") or "",
            "Centro": getattr(r, "centro", "") or "",
            "Area": getattr(r, "area", "") or "",
            "Numero_equipo": getattr(r, "numero_equipo", "") or "",
            "Equipo": getattr(r, "equipo", "") or "",
            "Modo_falla": _modo_falla(r),
            "Causas": " | ".join(_causas_adf(r)),
            "Tiempo_perdido_h": float(getattr(r, "tiempo_perdido_h", 0) or 0),
        })
    return salida.getvalue().encode("utf-8-sig")


def _panel_modos_falla(registros) -> None:
    st.markdown('<div class="analytics-divider"></div>', unsafe_allow_html=True)
    st.markdown("## 🧩 Modos de falla y causas")
    st.caption(
        "Análisis construido exclusivamente con información de los ADF registrados en RootMine. "
        "Los borradores se excluyen para no mezclar análisis incompletos."
    )

    realizados = [r for r in registros if (getattr(r, "estado", "") or "") != "Borrador"]
    if not realizados:
        st.info("Todavía no existen ADF realizados suficientes para analizar modos de falla.")
        return

    equipos = sorted({(r.equipo or "Sin descripción") for r in realizados})
    colf1, colf2 = st.columns([0.65, 0.35])
    with colf1:
        equipo_sel = st.selectbox(
            "Filtrar por equipo",
            ["Todos los equipos"] + equipos,
            key="indicador_modo_equipo",
        )
    with colf2:
        solo_repetidos = st.checkbox(
            "Solo modos repetidos",
            value=False,
            help="Muestra modos de falla con dos o más ADF dentro del filtro actual.",
        )

    filtrados = [
        r for r in realizados
        if equipo_sel == "Todos los equipos" or (r.equipo or "Sin descripción") == equipo_sel
    ]

    modos = Counter(_modo_falla(r) for r in filtrados)
    if solo_repetidos:
        modos = Counter({k:v for k,v in modos.items() if v >= 2})

    c1, c2, c3 = st.columns(3)
    c1.metric("ADF analizados", len(filtrados))
    c2.metric("Modos de falla distintos", len(modos))
    c3.metric("Modos repetidos", sum(1 for v in modos.values() if v >= 2))

    _grafico_barras_horizontal(
        dict(modos),
        "Modos de falla registrados",
        "Cantidad de ADF asociados a cada modo de falla.",
        max_items=12,
    )

    st.markdown("### Detalle para gestión")
    filas = []
    for modo, cantidad in modos.most_common():
        adfs_modo = [r for r in filtrados if _modo_falla(r) == modo]
        causas = []
        for r in adfs_modo:
            for causa in _causas_adf(r):
                if causa not in causas:
                    causas.append(causa)
        filas.append({
            "Modo de falla": modo,
            "ADF": cantidad,
            "Equipos": len({(r.numero_equipo or r.equipo or "") for r in adfs_modo}),
            "Causas registradas": " | ".join(causas[:5]) or "Sin causa estructurada",
            "Tiempo perdido (h)": round(sum(float(getattr(r, "tiempo_perdido_h", 0) or 0) for r in adfs_modo), 2),
        })

    if filas:
        st.dataframe(filas, use_container_width=True, hide_index=True)
    else:
        st.caption("No hay modos de falla que cumplan el filtro seleccionado.")

    if equipo_sel != "Todos los equipos" and filtrados:
        st.markdown(f"### Historial causal · {equipo_sel}")
        for r in sorted(filtrados, key=lambda x: getattr(x, "id", 0), reverse=True):
            with st.expander(f"ADF #{r.id} · {_modo_falla(r)}", expanded=False):
                st.write(f"**Estado:** {r.estado or 'Sin estado'}")
                st.write(f"**N° equipo:** {r.numero_equipo or 's/i'}")
                causas = _causas_adf(r)
                if causas:
                    st.write("**Causas / causa raíz registrada:**")
                    for causa in causas:
                        st.write(f"- {causa}")
                else:
                    st.caption("Sin causa estructurada registrada.")
                planes = _json(getattr(r, "plan_prevencion", ""), [])
                if isinstance(planes, list) and planes:
                    st.write("**Planes asociados:**")
                    for plan in plans if False else planes:
                        if isinstance(plan, dict):
                            st.write(f"- {plan.get('accion','Plan sin descripción')}")

    st.download_button(
        "⬇️ Descargar reporte de modos de falla (CSV)",
        data=_reporte_modos_csv(filtrados),
        file_name=(
            "RootMine_modos_falla_global.csv"
            if equipo_sel == "Todos los equipos"
            else "RootMine_modos_falla_" + "".join(c if c.isalnum() else "_" for c in equipo_sel)[:60] + ".csv"
        ),
        mime="text/csv",
        use_container_width=True,
    )


def mostrar_indicadores() -> None:
    registros = listar_adf()
    st.markdown('<div class="hero"><div class="eyebrow">NEURALMANT ANALYTICS</div><h1>Indicadores RootMine</h1><p>Vista ejecutiva de impacto, validaciones y cumplimiento de planes de acción.</p></div>', unsafe_allow_html=True)
    if not registros:
        st.info("Aún no hay datos suficientes para construir indicadores.")
        return

    area = st.selectbox("Filtrar por área", ["Todas"] + sorted({r.area for r in registros if r.area}))
    datos = [r for r in registros if area == "Todas" or r.area == area]
    acciones = [(r, a) for r in datos for a in _json(r.plan_prevencion, []) if isinstance(a, dict)]

    atrasados = sum(_estado_accion(a) == "Atrasado" for _, a in acciones)
    por_vencer = sum(_estado_accion(a) == "Por vencer" for _, a in acciones)
    ejecutados = sum(_estado_accion(a) == "Ejecutado" for _, a in acciones)
    sin_respaldo = sum(_pendiente_respaldo(a) for _, a in acciones)
    pendientes_val = sum((r.estado or "") in {"Pendiente Supervisor", "Pendiente Jefe"} for r in datos)
    tiempo_total = sum(float(getattr(r, "tiempo_perdido_h", 0) or 0) for r in datos)

    st.markdown("## Resumen ejecutivo")
    c1, c2, c3 = st.columns(3)
    _tarjeta(c1, "⏱️", "Tiempo perdido analizado", f"{tiempo_total:.1f} h", "blue", "Impacto acumulado de los ADF del filtro actual.")
    _tarjeta(c2, "🔴", "Planes atrasados", atrasados, "red", "Fecha compromiso vencida y acción aún no verificada.", "📋 Planes de acción", "Atrasados")
    _tarjeta(c3, "🟠", "Planes por vencer", por_vencer, "amber", "Compromisos que vencen durante los próximos 7 días.", "📋 Planes de acción", "Por vencer")

    c4, c5, c6 = st.columns(3)
    _tarjeta(c4, "📎", "Pendientes de respaldo", sin_respaldo, "purple", "Planes que todavía no tienen ejecución validada por evidencia.", "📋 Planes de acción", "Pendientes de respaldo")
    _tarjeta(c5, "✅", "Ejecutados verificados", ejecutados, "green", "Acciones cuya ejecución quedó respaldada/verificada.", "📋 Planes de acción", "Ejecutados")
    _tarjeta(c6, "🛡️", "ADF pendientes de validación", pendientes_val, "cyan", "ADF esperando visto bueno de Supervisor o Jefe.", "✅ Validaciones", "Pendientes")

    st.markdown('<div class="analytics-divider"></div>', unsafe_allow_html=True)

    col1, col2 = st.columns([1.18, 0.82], gap="large")
    with col1:
        t_area = defaultdict(float)
        for r in datos:
            t_area[r.area or "Sin área"] += float(getattr(r, "tiempo_perdido_h", 0) or 0)
        _grafico_barras_horizontal(t_area, "Tiempo perdido analizado por área", "Horas acumuladas provenientes de los ADF registrados.")
    with col2:
        conteo = Counter(_estado_accion(a) for _, a in acciones)
        _grafico_estado_planes(conteo)

    col3, col4 = st.columns(2, gap="large")
    with col3:
        por_equipo = defaultdict(float)
        for r in datos:
            eq = r.equipo or "Sin descripción de equipo"
            por_equipo[eq] += float(getattr(r, "tiempo_perdido_h", 0) or 0)
        _grafico_barras_horizontal(por_equipo, "Equipos con mayor tiempo perdido", max_items=8)
    with col4:
        planes_equipo = Counter()
        for r, _a in acciones:
            eq = r.equipo or "Sin descripción de equipo"
            planes_equipo[eq] += 1
        _grafico_barras_horizontal(dict(planes_equipo), "Equipos con más planes de acción", max_items=8)

    _panel_modos_falla(datos)
