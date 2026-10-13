from io import BytesIO
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from database import trabajos as db

def _fecha(valor):
    if not valor:return 'Sin actualización'
    return datetime.fromisoformat(valor).replace(tzinfo=ZoneInfo('UTC')).astimezone(ZoneInfo('America/Santiago')).strftime('%d/%m/%Y %H:%M')

def generar_pdf(correo,programa,corte,fotos=False):
    # Revalidate visibility even when caller supplies a previously downloaded snapshot.
    db.trabajos(correo,programa)
    fuentes=Path(__file__).resolve().parents[1]/'assets'/'fonts'
    if 'Trabajo-Regular' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('Trabajo-Regular',str(fuentes/'Reporte-Regular.ttf')))
        pdfmetrics.registerFont(TTFont('Trabajo-Bold',str(fuentes/'Reporte-Bold.ttf')))
    estilos=getSampleStyleSheet()
    for estilo in estilos.byName.values():
        estilo.textColor=colors.HexColor('#003087')
        estilo.fontName='Trabajo-Bold' if estilo.name.startswith(('Heading','Title')) else 'Trabajo-Regular'
    normal=estilos['BodyText'];normal.fontSize=9;normal.leading=13
    def p(texto,estilo=normal):return Paragraph(escape(str(texto)).replace('\n','<br/>'),estilo)
    out=BytesIO();doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=32,leftMargin=32,topMargin=32,bottomMargin=32)
    elementos=[p('NeuralMant · Seguimiento de trabajos',estilos['Title']),p(corte['titulo'],estilos['Heading2']),
        p(f"Centro {corte['centro']} · {corte['fecha']} · Turno {corte['turno']}"),p(f"Corte: {_fecha(corte['generado'])} (Chile) · Registrado por {corte['nombre']}"),Spacer(1,12)]
    if corte.get('comentario'):elementos.extend([p('Entrega de turno',estilos['Heading2']),p(corte['comentario'])])
    elementos.append(p('Preparación para la partida',estilos['Heading2']))
    for linea in corte['lineas']:elementos.append(p(f"{linea['línea']}: {linea['partida']} · {linea['pruebas']} · Avance medio informado: {str(linea['avance'])+'%' if linea['avance'] is not None else 'Sin porcentaje'}"))
    elementos.append(p('La condición de partida se basa en los trabajos registrados en este programa; no sustituye la verificación operacional de la planta.'))
    for d in corte['trabajos']:
        elementos.extend([Spacer(1,12),p(f"#{d['id']} · {d['linea']} · {d['equipo']}",estilos['Heading2']),p(d['descripcion']),p(f"OT: {d.get('ot') or 'Sin OT informada'} · Ejecutor: {d.get('ejecutor') or 'Sin ejecutor informado'}"),
            p(f"{d['area']} · Supervisor: {d['supervisor']}"),p(f"Estado: {d['estado']} · Avance: {str(d['avance'])+'%' if d['avance'] is not None else 'Sin porcentaje'} · Prueba: {d['prueba']}"),
            p('Pendientes/bloqueos: '+(d['pendiente'] or 'Sin pendientes informados')),
            p('Origen del avance: '+{'estimado_etapas':'Estimado por etapas','informado_supervisor':'Informado por supervisor','estado_supervisor':'Estado confirmado por supervisor'}.get(d.get('origen_avance'),'Estado inicial / anterior')),p('Último mensaje: '+(d.get('ultimo_mensaje') or 'Sin mensaje')),p('Hallazgos: '+(d['hallazgos'] or 'Sin hallazgos informados')),p('Prueba/resultado: '+(d['detalle_prueba'] or 'Sin resultado informado')),
            p(f"Última actualización: {_fecha(d['actualizado'])} · {d['autor'] or 'Sin actualización'}")])
        if fotos:
            permitidas=set(d.get('fotos',[]))
            imagenes=[f for f in db.evidencia(correo,programa,d['id']) if f['id'] in permitidas][-2:]
            for f in imagenes:
                imagen=Image(BytesIO(f['contenido']));imagen._restrictSize(470,240)
                elementos.extend([Spacer(1,6),imagen,p(f"Foto: {f['nombre']} · {f['usuario']} · {_fecha(f['fecha'].isoformat())}")])
    def pie(canvas,document):
        canvas.setFont('Trabajo-Regular',8);canvas.setFillColor(colors.HexColor('#003087'));canvas.drawRightString(A4[0]-32,18,f'NeuralMant · Página {document.page}')
    doc.build(elementos,onFirstPage=pie,onLaterPages=pie)
    return out.getvalue()
