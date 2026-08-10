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


def _dividir_completo(texto: str, limite: int = 43) -> list[str]:
    """Envuelve el texto sin cortarlo ni agregar puntos suspensivos."""
    palabras = " ".join(str(texto).split()).split()
    if not palabras:
        return ["Sin causa propuesta"]
    lineas: list[str] = []
    actual = ""
    for palabra in palabras:
        candidato = f"{actual} {palabra}".strip()
        if len(candidato) <= limite or not actual:
            actual = candidato
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def _lineas_categoria(ishikawa: dict, clave: str) -> list[tuple[str, bool]]:
    causas = ishikawa.get(clave, [])
    if not causas:
        return [("Sin causas propuestas", False)]
    salida: list[tuple[str, bool]] = []
    for indice, causa in enumerate(causas, start=1):
        texto = causa.get("causa", "") if isinstance(causa, dict) else str(causa)
        envueltas = _dividir_completo(texto, 42)
        for numero_linea, linea in enumerate(envueltas):
            prefijo = f"{indice}. " if numero_linea == 0 else "   "
            salida.append((prefijo + linea, numero_linea == 0))
        if indice < len(causas):
            salida.append(("", False))
    return salida


def construir_svg_ishikawa(efecto: str, ishikawa: dict) -> str:
    """Espina 6M legible: las cajas crecen según el texto y nunca lo recortan."""
    # Se reserva un bloque completo a la derecha para que el EFECTO nunca se recorte.
    ancho = 1840
    box_w = 430
    title_h = 42
    line_h = 19
    pad = 16
    posiciones_x = [260, 760, 1260]

    lineas_por_cat = {}
    alturas = {}
    for categoria, clave, arriba in ORDEN:
        lineas = _lineas_categoria(ishikawa, clave)
        lineas_por_cat[clave] = lineas
        alturas[clave] = title_h + pad * 2 + max(1, len(lineas)) * line_h

    max_arriba = max(alturas[k] for _, k, a in ORDEN if a)
    max_abajo = max(alturas[k] for _, k, a in ORDEN if not a)
    margen = 36
    separacion = 74
    y_centro = margen + max_arriba + separacion
    alto = int(y_centro + separacion + max_abajo + margen)
    x_inicio, x_fin = 75, 1435

    partes = [
        f'<svg viewBox="0 0 {ancho} {alto}" width="100%" preserveAspectRatio="xMidYMid meet" style="overflow:visible;display:block" xmlns="http://www.w3.org/2000/svg">',
        '<rect width="100%" height="100%" rx="22" fill="#ffffff" stroke="#d9e2ef"/>',
        f'<line x1="{x_inicio}" y1="{y_centro}" x2="{x_fin}" y2="{y_centro}" stroke="#173b73" stroke-width="7" stroke-linecap="round"/>',
        f'<polygon points="{x_fin},{y_centro-24} {x_fin+48},{y_centro} {x_fin},{y_centro+24}" fill="#173b73"/>',
    ]

    # Efecto final con alto automático.
    efecto_w = 300
    efecto_x = x_fin + 48
    efecto_lineas = _dividir_completo(efecto, 39)
    efecto_h = max(118, 70 + len(efecto_lineas) * 22)
    efecto_y = y_centro - efecto_h / 2
    partes += [
        f'<rect x="{efecto_x}" y="{efecto_y}" width="{efecto_w}" height="{efecto_h}" rx="16" fill="#285fd5"/>',
        f'<text x="{efecto_x + efecto_w/2}" y="{efecto_y+29}" text-anchor="middle" fill="#fff" font-size="16" font-weight="800">EFECTO</text>',
        f'<line x1="{efecto_x+22}" y1="{efecto_y+43}" x2="{efecto_x+efecto_w-22}" y2="{efecto_y+43}" stroke="rgba(255,255,255,.42)" stroke-width="1"/>',
    ]
    for i, linea in enumerate(efecto_lineas):
        partes.append(f'<text x="{efecto_x + efecto_w/2}" y="{efecto_y+69+i*22}" text-anchor="middle" fill="#fff" font-size="13.5" font-weight="550">{escape(linea)}</text>')

    for indice, (categoria, clave, arriba) in enumerate(ORDEN):
        x_centro = posiciones_x[indice % 3]
        h = alturas[clave]
        if arriba:
            y_box = margen
            y_branch = y_box + h
            y_spine = y_centro
        else:
            y_box = y_centro + separacion
            y_branch = y_box
            y_spine = y_centro

        # Rama diagonal desde la caja hacia la espina.
        direction = 90 if arriba else -90
        partes.append(
            f'<line x1="{x_centro}" y1="{y_branch}" x2="{x_centro + direction}" y2="{y_spine}" '
            f'stroke="#2b62cf" stroke-width="4" stroke-linecap="round"/>'
        )

        x_box = x_centro - box_w / 2
        partes.append(f'<rect x="{x_box}" y="{y_box}" width="{box_w}" height="{h}" rx="13" fill="#f8fbff" stroke="#91a9c7" stroke-width="1.5"/>')
        partes.append(f'<rect x="{x_box}" y="{y_box}" width="{box_w}" height="{title_h}" rx="13" fill="#1f4b8f"/>')
        # Cuadrar la parte inferior de la cabecera.
        partes.append(f'<rect x="{x_box}" y="{y_box+title_h-12}" width="{box_w}" height="12" fill="#1f4b8f"/>')
        partes.append(f'<text x="{x_centro}" y="{y_box+27}" text-anchor="middle" fill="#fff" font-size="15" font-weight="700">{escape(categoria)}</text>')

        text_y = y_box + title_h + pad + 13
        for linea, primera in lineas_por_cat[clave]:
            if not linea:
                text_y += 5
                continue
            peso = ' font-weight="650"' if primera else ''
            partes.append(f'<text x="{x_box+17}" y="{text_y}" fill="#20324c" font-size="12.5"{peso}>{escape(linea)}</text>')
            text_y += line_h

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
    st.markdown("#### Matriz de causas 6M")
    st.dataframe(
        construir_filas(ishikawa),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Categoría": st.column_config.TextColumn(width="small"),
            "Causa probable": st.column_config.TextColumn(width="large"),
            "Mecanismo": st.column_config.TextColumn(width="large"),
            "Prioridad": st.column_config.TextColumn(width="small"),
        },
    )
    with st.expander("Ver diagrama en espina de pescado", expanded=True):
        st.markdown(construir_svg_ishikawa(efecto, ishikawa), unsafe_allow_html=True)
        st.caption("Las cajas del diagrama se ajustan automáticamente a la extensión del texto; ninguna causa se trunca.")
