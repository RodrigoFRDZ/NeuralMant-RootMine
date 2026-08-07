from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


AZUL = colors.HexColor("#07182b")
AZUL_2 = colors.HexColor("#1592ff")
GRIS = colors.HexColor("#edf2f8")
ROJO = colors.HexColor("#ff7a00")


def _texto(valor: Any) -> str:
    return str(valor or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _encabezado_pie(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFillColor(AZUL)
    canvas.rect(0, A4[1] - 1.25 * cm, A4[0], 1.25 * cm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(1.5 * cm, A4[1] - 0.8 * cm, "NeuralMant Suite · RootMine | Informe de Análisis de Falla")
    canvas.setFillColor(colors.HexColor("#566579"))
    canvas.setFont("Helvetica", 8)
    canvas.drawString(1.45 * cm, 0.75 * cm, "Generado por GearBot · Created by Rodrigo Fernández")
    canvas.drawRightString(A4[0] - 1.4 * cm, 0.75 * cm, f"Página {doc.page}")
    canvas.restoreState()


def _estilos():
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle(
            "titulo", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=22, leading=26, textColor=AZUL, alignment=TA_LEFT,
            spaceAfter=10,
        ),
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=15, leading=19, textColor=AZUL, spaceBefore=10, spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=11, leading=14, textColor=AZUL_2, spaceBefore=7, spaceAfter=5,
        ),
        "normal": ParagraphStyle(
            "normal", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9.5, leading=13, textColor=colors.HexColor("#26374d"),
            alignment=TA_LEFT,
        ),
        "pequeno": ParagraphStyle(
            "pequeno", parent=base["BodyText"], fontName="Helvetica",
            fontSize=8, leading=10, textColor=colors.HexColor("#566579"),
        ),
        "centro": ParagraphStyle(
            "centro", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=12, leading=15, textColor=colors.white, alignment=TA_CENTER,
        ),
    }


def _tabla_datos(datos: dict, estilos: dict):
    filas = [
        ["Área", _texto(datos.get("area")), "Equipo", _texto(datos.get("equipo"))],
        ["Aviso SAP", _texto(datos.get("aviso_sap") or "No informado"), "Responsable", _texto(datos.get("creado_por"))],
        ["Fenómeno", Paragraph(_texto(datos.get("efecto")), estilos["normal"]), "Estado", "Preliminar / editable"],
    ]
    tabla = Table(filas, colWidths=[2.1*cm, 5.4*cm, 2.4*cm, 7.1*cm])
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), AZUL),
        ("BACKGROUND", (2,0), (2,-1), AZUL),
        ("TEXTCOLOR", (0,0), (0,-1), colors.white),
        ("TEXTCOLOR", (2,0), (2,-1), colors.white),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8.5),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e2")),
        ("BACKGROUND", (1,0), (1,-1), colors.white),
        ("BACKGROUND", (3,0), (3,-1), colors.white),
        ("TOPPADDING", (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ]))
    return tabla


def _ishikawa_tabla(ishikawa: dict, estilos: dict):
    categorias = [
        ("Máquina", "Máquina"), ("Método", "Método"),
        ("Mano de obra", "Mano de obra"), ("Material", "Material"),
        ("Medición", "Medición"), ("Medio ambiente", "Medio ambiente"),
    ]
    celdas = []
    for categoria, clave in categorias:
        items = ishikawa.get(clave, [])
        lineas = []
        for item in items:
            causa = item.get("causa", "") if isinstance(item, dict) else str(item)
            lineas.append(f"• {_texto(causa)}")
        contenido = "<br/>".join(lineas) or "Sin causas seleccionadas"
        celdas.append([
            Paragraph(categoria, estilos["centro"]),
            Paragraph(contenido, estilos["normal"]),
        ])
    tabla = Table(celdas, colWidths=[4.1*cm, 13.2*cm], repeatRows=0)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), AZUL_2),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e2")),
        ("TOPPADDING", (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ]))
    return tabla


def generar_pdf_adf(datos: dict, imagen_bytes: bytes | None = None) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=1.45*cm, leftMargin=1.45*cm,
        topMargin=1.75*cm, bottomMargin=1.35*cm,
        title=f"ADF - {datos.get('equipo', '')}",
        author="Rodrigo Fernández · NeuralMant RootMine",
    )
    e = _estilos()
    story = [
        Spacer(1, 0.25*cm),
        Paragraph("NEURALMANT SUITE · ROOTMINE", e["h2"]),
        Paragraph(_texto(datos.get("titulo") or "INFORME DE ANÁLISIS DE FALLA"), e["titulo"]),
        Paragraph("Análisis Inteligente de Causa Raíz", e["pequeno"]),
        Spacer(1, 0.15*cm),
        _tabla_datos(datos, e),
        Spacer(1, 0.35*cm),
        Paragraph("1. Resumen ejecutivo", e["h1"]),
        Paragraph(_texto(datos.get("resumen_ejecutivo")), e["normal"]),
        Paragraph("2. Descripción del evento", e["h1"]),
        Paragraph(_texto(datos.get("descripcion_evento") or datos.get("relato_original")), e["normal"]),
        Paragraph("3. Evidencia fotográfica de la falla", e["h1"]),
    ]

    if imagen_bytes:
        try:
            imagen = Image(BytesIO(imagen_bytes), width=15.5*cm, height=8.5*cm, kind="proportional")
            story.extend([imagen, Spacer(1, 0.2*cm)])
        except Exception:
            story.append(Paragraph("No fue posible incorporar la imagen adjunta.", e["pequeno"]))
    else:
        espacio = Table([[Paragraph("ESPACIO PARA INCORPORAR IMAGEN DE LA FALLA", e["centro"])]], colWidths=[17.3*cm], rowHeights=[8*cm])
        espacio.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#8da0b9")),
            ("BOX", (0,0), (-1,-1), 1, AZUL),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ]))
        story.append(espacio)

    story.extend([
        Paragraph("4. Principio de funcionamiento", e["h1"]),
        Paragraph(_texto(datos.get("principio_funcionamiento")), e["normal"]),
        Paragraph("5. Fenómeno investigado", e["h1"]),
        Paragraph(_texto(datos.get("fenomeno_investigado") or datos.get("efecto")), e["normal"]),
        Paragraph("6. Análisis Ishikawa 6M", e["h1"]),
        Paragraph(_texto(datos.get("sintesis_ishikawa")), e["normal"]),
        Spacer(1, 0.2*cm),
        _ishikawa_tabla(datos.get("ishikawa_validado", {}), e),
        Spacer(1, 0.35*cm),
        Paragraph("7. Profundización causal - 5 Porqués", e["h1"]),
    ])

    for i, cadena in enumerate(datos.get("cadenas_causales", []), start=1):
        elementos = [Paragraph(f"Cadena {i}: {_texto(cadena.get('causa'))}", e["h2"])]
        filas = [["Nivel", "Pregunta", "Respuesta validada", "Justificación / evidencia"]]
        for nivel in cadena.get("niveles", []):
            apoyo = "<b>Justificación:</b> " + _texto(nivel.get("justificacion", ""))
            evidencia = _texto(nivel.get("evidencia", ""))
            if evidencia:
                apoyo += "<br/><b>Evidencia:</b> " + evidencia
            filas.append([
                str(nivel.get("nivel", "")),
                Paragraph(_texto(nivel.get("pregunta")), e["pequeno"]),
                Paragraph(_texto(nivel.get("respuesta")), e["pequeno"]),
                Paragraph(apoyo, e["pequeno"]),
            ])
        tabla = Table(filas, colWidths=[1.1*cm, 5.1*cm, 5.2*cm, 5.9*cm], repeatRows=1)
        tabla.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), AZUL),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 7.5),
            ("GRID", (0,0), (-1,-1), 0.45, colors.HexColor("#bcc8d8")),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("TOPPADDING", (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]))
        elementos.extend([tabla, Spacer(1, 0.25*cm)])
        story.append(KeepTogether(elementos))

    story.extend([
        Paragraph("8. Conclusión técnica", e["h1"]),
        Paragraph(_texto(datos.get("conclusion_tecnica")), e["normal"]),
        Paragraph("9. Plan de prevención", e["h1"]),
    ])
    acciones = datos.get("plan_prevencion", [])
    filas = [["Acción", "Objetivo", "Relación con causa", "Responsable", "Plazo", "Evidencia"]]
    for accion in acciones:
        filas.append([
            Paragraph(_texto(accion.get("accion")), e["pequeno"]),
            Paragraph(_texto(accion.get("objetivo")), e["pequeno"]),
            Paragraph(_texto(accion.get("relacion_con_causa")), e["pequeno"]),
            Paragraph(_texto(accion.get("responsable_sugerido")), e["pequeno"]),
            Paragraph(_texto(accion.get("plazo_sugerido")), e["pequeno"]),
            Paragraph(_texto(accion.get("evidencia_de_implementacion")), e["pequeno"]),
        ])
    tabla_acciones = Table(filas, colWidths=[3.6*cm, 3.1*cm, 3.5*cm, 2.2*cm, 1.8*cm, 3.1*cm], repeatRows=1)
    tabla_acciones.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), AZUL),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 7),
        ("GRID", (0,0), (-1,-1), 0.45, colors.HexColor("#bcc8d8")),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.extend([
        tabla_acciones,
        Paragraph("10. Lección aprendida", e["h1"]),
        Paragraph(_texto(datos.get("leccion_aprendida")), e["normal"]),
    ])

    pendientes = datos.get("pendientes_validacion", [])
    if pendientes:
        story.append(Paragraph("Pendientes de validación", e["h1"]))
        for pendiente in pendientes:
            story.append(Paragraph(f"• {_texto(pendiente)}", e["normal"]))

    story.extend([
        Spacer(1, 0.5*cm),
        Paragraph(
            "Nota: El contenido generado por IA es una guía técnica y debe ser validado por el equipo investigador antes de su aprobación.",
            e["pequeno"],
        ),
    ])
    doc.build(story, onFirstPage=_encabezado_pie, onLaterPages=_encabezado_pie)
    return buffer.getvalue()
