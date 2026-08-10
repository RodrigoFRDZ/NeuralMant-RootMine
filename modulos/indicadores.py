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
            eq = getattr(r, "numero_equipo", "") or r.equipo or "Sin equipo"
            por_equipo[eq] += float(getattr(r, "tiempo_perdido_h", 0) or 0)
        _grafico_barras_horizontal(por_equipo, "Equipos con mayor tiempo perdido", max_items=8)
    with col4:
        planes_equipo = Counter()
        for r, _a in acciones:
            eq = getattr(r, "numero_equipo", "") or r.equipo or "Sin equipo"
            planes_equipo[eq] += 1
        _grafico_barras_horizontal(dict(planes_equipo), "Equipos con más planes de acción", max_items=8)
