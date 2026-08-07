from html import escape

import streamlit as st


ORDEN = [
    ("Máquina", "maquina", True),
    ("Método", "metodo", True),
    ("Mano de obra", "mano_obra", True),
    ("Material", "material", False),
    ("Medición", "medicion", False),
    ("Medio ambiente", "medio_ambiente", False),
]


def _resumir(texto: str, limite: int = 34) -> str:
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def _dividir(texto: str, limite: int = 28, max_lineas: int = 2) -> list[str]:
    palabras = " ".join(str(texto).split()).split()
    lineas: list[str] = []
    actual = ""
    for palabra in palabras:
        candidato = f"{actual} {palabra}".strip()
        if len(candidato) <= limite:
            actual = candidato
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
            if len(lineas) == max_lineas - 1:
                break
    if actual and len(lineas) < max_lineas:
        lineas.append(actual)
    texto_usado = " ".join(lineas)
    texto_original = " ".join(palabras)
    if len(texto_usado) < len(texto_original) and lineas:
        lineas[-1] = _resumir(lineas[-1], limite)
    return lineas or ["Sin causa"]


def construir_svg_ishikawa(efecto: str, ishikawa: dict) -> str:
    """Vista compacta para el informe/consulta, limitada a dos causas por categoría."""
    ancho, alto = 1200, 620
    x_inicio, x_fin, y_centro = 105, 955, 310
    posiciones = [235, 465, 695]
    partes = [
        f'<svg viewBox="0 0 {ancho} {alto}" xmlns="http://www.w3.org/2000/svg">',
        '<rect width="100%" height="100%" rx="20" fill="#ffffff" stroke="#d9e2ef"/>',
        f'<line x1="{x_inicio}" y1="{y_centro}" x2="{x_fin}" y2="{y_centro}" stroke="#173b73" stroke-width="7" stroke-linecap="round"/>',
        f'<polygon points="{x_fin},{y_centro-24} {x_fin+48},{y_centro} {x_fin},{y_centro+24}" fill="#173b73"/>',
        f'<rect x="{x_fin+42}" y="{y_centro-68}" width="182" height="136" rx="14" fill="#285fd5"/>',
        f'<text x="{x_fin+133}" y="{y_centro-34}" text-anchor="middle" fill="#fff" font-size="16" font-weight="700">EFECTO</text>',
    ]
    for i, linea in enumerate(_dividir(efecto, 22, 3)):
        partes.append(f'<text x="{x_fin+133}" y="{y_centro-3+i*22}" text-anchor="middle" fill="#fff" font-size="13">{escape(linea)}</text>')

    for indice, (categoria, clave, arriba) in enumerate(ORDEN):
        x = posiciones[indice % 3]
        y_extremo = 78 if arriba else 542
        color = "#1f4b8f" if arriba else "#2b62cf"
        partes.append(f'<line x1="{x}" y1="{y_extremo}" x2="{x+110}" y2="{y_centro}" stroke="{color}" stroke-width="4" stroke-linecap="round"/>')
        caja_y = 35 if arriba else 540
        partes.append(f'<rect x="{x-92}" y="{caja_y-21}" width="184" height="42" rx="10" fill="{color}"/>')
        partes.append(f'<text x="{x}" y="{caja_y+6}" text-anchor="middle" fill="#fff" font-size="15" font-weight="700">{escape(categoria)}</text>')

        causas = ishikawa.get(clave, [])[:2]
        for j, causa in enumerate(causas):
            texto = causa.get("causa", "") if isinstance(causa, dict) else str(causa)
            base_y = (126 + j * 72) if arriba else (493 - j * 72)
            base_x = x + 28 + j * 25
            partes.append(f'<line x1="{base_x}" y1="{base_y}" x2="{base_x+105}" y2="{base_y}" stroke="#9aacC5" stroke-width="2"/>')
            for k, linea in enumerate(_dividir(texto, 26, 2)):
                partes.append(f'<text x="{base_x+8}" y="{base_y-9+k*16}" fill="#20324c" font-size="11.5">{escape(linea)}</text>')
    partes.append('</svg>')
    return "".join(partes)


def construir_filas(ishikawa: dict) -> list[dict]:
    filas: list[dict] = []
    for categoria, clave, _ in ORDEN:
        causas = ishikawa.get(clave, [])
        if not causas:
            filas.append({
                "Categoría": categoria,
                "Causa probable": "Sin causas propuestas",
                "Mecanismo": "",
                "Prioridad": "",
            })
            continue
        for causa in causas:
            filas.append({
                "Categoría": categoria,
                "Causa probable": causa.get("causa", ""),
                "Mecanismo": causa.get("mecanismo", ""),
                "Prioridad": causa.get("prioridad_revision", ""),
            })
    return filas


def mostrar_ishikawa(efecto: str, ishikawa: dict) -> None:
    """Presenta primero una tabla uniforme y deja la espina como vista complementaria."""
    st.markdown("#### Matriz de causas 6M")
    st.dataframe(
        construir_filas(ishikawa),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Categoría": st.column_config.TextColumn(width="small"),
            "Causa probable": st.column_config.TextColumn(width="medium"),
            "Mecanismo": st.column_config.TextColumn(width="large"),
            "Prioridad": st.column_config.TextColumn(width="small"),
        },
    )
    with st.expander("Ver diagrama compacto en espina de pescado", expanded=False):
        st.markdown(construir_svg_ishikawa(efecto, ishikawa), unsafe_allow_html=True)
        st.caption("La vista compacta muestra hasta dos causas por categoría. La tabla conserva el detalle completo.")
