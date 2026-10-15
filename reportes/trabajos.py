from io import BytesIO
from pathlib import Path
from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak
from reportlab.lib.pagesizes import A4
from database import trabajos as db
from motores.foco_partida import focos

def _fecha(valor):
    if not valor:return 'Sin actualización'
    t=datetime.fromisoformat(str(valor).replace('Z','+00:00'))
    if t.tzinfo is None:t=t.replace(tzinfo=ZoneInfo('UTC'))
    return t.astimezone(ZoneInfo('America/Santiago')).strftime('%d/%m/%Y %H:%M')

def generar_pdf(correo,programa,corte,fotos=False):
    db.trabajos(correo,programa)
    imagenes={}
    if fotos:
        for d in corte['trabajos']:
            permitidas=set(d.get('fotos',[]))
            if permitidas:imagenes[d['id']]=[f for f in db.evidencia(correo,programa,d['id']) if f['id'] in permitidas][-2:]
    return render_pdf(corte,imagenes)

def render_pdf(corte,imagenes=None):
    imagenes=imagenes or {};filas=corte['trabajos'];novedades=corte.get('novedades_area',[]);analisis=focos(filas,novedades)
    fuentes=Path(__file__).resolve().parents[1]/'assets/fonts'
    if 'Trabajo-Regular' not in pdfmetrics.getRegisteredFontNames():
        for tipo,archivo in [('Regular','Reporte-Regular.ttf'),('Bold','Reporte-Bold.ttf')]:pdfmetrics.registerFont(TTFont('Trabajo-'+tipo,str(fuentes/archivo)))
    tinta=colors.HexColor('#25313a');naranja=colors.HexColor('#df791c');gris=colors.HexColor('#596571');linea=colors.HexColor('#dde3e8')
    estilos=getSampleStyleSheet()
    for estilo in estilos.byName.values():
        estilo.textColor=tinta;estilo.fontName='Trabajo-Bold' if estilo.name.startswith(('Heading','Title')) else 'Trabajo-Regular'
    estilos['Title'].fontSize=22;estilos['Title'].leading=27;estilos['Title'].alignment=0
    estilos['Heading2'].fontSize=13;estilos['Heading2'].leading=17;estilos['Heading2'].spaceBefore=14;estilos['Heading2'].spaceAfter=8
    estilos['Heading3'].fontSize=10;estilos['Heading3'].leading=14;estilos['Heading3'].spaceBefore=10
    normal=estilos['BodyText'];normal.fontSize=9;normal.leading=13
    pequeño=ParagraphStyle('Nota',parent=normal,fontSize=8,leading=11,textColor=gris,spaceAfter=5)
    dato=ParagraphStyle('Indicador',parent=normal,fontName='Trabajo-Bold',fontSize=18,leading=23)
    eyebrow=ParagraphStyle('Marca',parent=normal,fontName='Trabajo-Bold',fontSize=9,leading=13,textColor=naranja,spaceAfter=10)
    def p(texto,estilo=normal):return Paragraph(escape(str(texto)).replace('\n','<br/>'),estilo)
    out=BytesIO();ancho=A4[0]-72
    doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=36,leftMargin=36,topMargin=38,bottomMargin=38,title='NeuralMant - Informe de ejecución y preparación operacional',author='NeuralMant',subject=corte['titulo'])
    elementos=[p('NEURALMANT  /  CONTROL DE MANTENIMIENTO',eyebrow),p('Informe de ejecución y preparación operacional',estilos['Title']),p(corte['titulo'],estilos['Heading2']),
        p(f"Centro {corte['centro']} · {corte['fecha']} · Turno {corte['turno']}",pequeño),p(f"Corte: {_fecha(corte['generado'])} (Chile) · Preparado por {corte['nombre']}",pequeño),Spacer(1,12)]
    abiertos=[a for a in novedades if a.get('estado')=='Abierto' and not a.get('resuelve')]
    indicadores=[(f"{sum(d['estado']=='Terminado' for d in filas)} / {len(filas)}",'Actividades terminadas'),(str(sum(d['estado']=='Detenido' for d in filas)),'Trabajos detenidos'),(str(sum(d['prueba'] not in ('Aprobada','No requerida') for d in filas)),'Pruebas por resolver'),(str(len(abiertos)),'Novedades de área abiertas')]
    tabla=Table([[ [p(v,dato),p(t,pequeño)] for v,t in indicadores]],colWidths=[ancho/4]*4)
    tabla.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#f2f4f6')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),8),('LINEABOVE',(0,0),(-1,0),2,naranja)]));elementos.append(tabla)
    elementos.extend([p('01  Resumen ejecutivo',estilos['Heading2']),p(corte.get('comentario') or 'Sin resumen adicional registrado.')])
    def lista_focos(titulo,items,vacio):
        elementos.append(p(titulo,estilos['Heading2']))
        if not items:elementos.append(p(vacio,pequeño))
        for i,f in enumerate(items,1):elementos.extend([p(f"{i}. {f['referencia']}",estilos['Heading3']),p(f['detalle']),p(f['accion'],pequeño)])
    lista_focos('02  Focos previos a la partida',analisis['partida'],'Sin focos identificados en los registros actuales. No equivale a autorización de partida.')
    elementos.append(p('Las prioridades se derivan de lo informado. Requieren validación operacional; un trabajo terminado no confirma una prueba aprobada.',pequeño))
    elementos.append(p('03  Seguridad y calidad por área',estilos['Heading2']))
    criticos=[a for a in novedades if a['categoria'] in ('Seguridad','Calidad')]
    if not criticos:elementos.append(p('Sin novedades de área clasificadas en seguridad o calidad. Revisar también los focos asociados a actividades.',pequeño))
    for a in criticos:
        elementos.extend([p(f"{a['area']} · {a['categoria']} · {a['estado']}",estilos['Heading3']),p(a['mensaje']),p(f"{a['nombre']} · {_fecha(a['fecha'])} · Impacto: {a['impacto']} · {a.get('clasificacion','Informada')}",pequeño)])
        if a.get('cierre'):elementos.append(p('Resolución informada por '+a['cierre']['nombre']+': '+a['cierre']['mensaje'],pequeño))
    lista_focos('04  Retrasos y entregas',analisis['retrasos'],'No se identificaron retrasos informados en los registros. No se confirma cumplimiento horario si faltan horas reales de entrega.')
    elementos.append(p('No se clasifica una entrega como tardía por la hora en que se escribió el comentario. Los horarios planificados y la entrega real deben confirmarse para cuantificar una demora.',pequeño))
    lista_focos('05  Seguimiento durante la semana',analisis['semana'],'Sin focos semanales específicos identificados en los registros actuales.')
    if corte.get('sugerencias') and not corte.get('sugerencias_automaticas'):
        elementos.extend([p('Acciones y sugerencias de la entrega',estilos['Heading3']),p(corte['sugerencias'])])
    elementos.append(p('06  Ejecución y pruebas por área',estilos['Heading2']))
    datos=[[p(x,pequeño) for x in ['Área','Terminadas','Prueba aprobada','Prueba por resolver']]]
    for area in sorted({d['area'] for d in filas}):
        grupo=[d for d in filas if d['area']==area]
        datos.append([p(area),p(f"{sum(d['estado']=='Terminado' for d in grupo)} / {len(grupo)}"),p(str(sum(d['prueba']=='Aprobada' for d in grupo))),p(str(sum(d['prueba'] not in ('Aprobada','No requerida') for d in grupo)))])
    tabla=Table(datos,colWidths=[ancho*.31,ancho*.21,ancho*.23,ancho*.25],repeatRows=1,hAlign='LEFT')
    tabla.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf0f2')),('LINEBELOW',(0,0),(-1,0),1,naranja),('LINEBELOW',(0,1),(-1,-1),.4,linea),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]));elementos.append(tabla)
    elementos.extend([PageBreak(),p('ANEXO  /  TRAZABILIDAD DE LA EJECUCIÓN',eyebrow),p('Detalle de actividades',estilos['Title'])])
    for d in filas:
        elementos.extend([p(d['descripcion'],estilos['Heading2']),p(f"{d['area']}"+(' · '+d['linea'] if d.get('linea') else '')+(' · '+d['equipo'] if d.get('equipo') else ''),pequeño),p(f"OT: {d.get('ot') or 'Sin OT informada'} · Ejecutor: {d.get('ejecutor') or 'Sin ejecutor informado'}",pequeño),
            p(f"Estado: {d['estado']} · Avance: {str(d['avance'])+'%' if d['avance'] is not None else 'Sin porcentaje'} · Prueba: {d['prueba']}"),p('Origen del avance: '+{'estimado_etapas':'Estimado por etapas','informado_supervisor':'Informado por supervisor','estado_supervisor':'Estado confirmado por supervisor'}.get(d.get('origen_avance'),'Estado inicial / anterior'),pequeño),p('Pendientes/bloqueos: '+(d.get('pendiente') or 'Sin pendientes informados')),p('Hallazgos: '+(d.get('hallazgos') or 'Sin hallazgos informados')),p('Prueba/resultado: '+(d.get('detalle_prueba') or 'Sin resultado informado')),p('Último mensaje: '+(d.get('ultimo_mensaje') or 'Sin mensaje')),p(f"Última actualización: {_fecha(d.get('actualizado'))} · {d.get('autor') or 'Sin actualización'}",pequeño)])
        elementos.append(p('Bitácora de la actividad',estilos['Heading3']))
        for h in d.get('historial',[]):
            if not corte.get('final') and h.get('automatico'):continue
            elementos.append(p(f"{_fecha(h['fecha'])} · {h.get('nombre') or h.get('usuario')} · {h.get('estado','')} · Avance: {str(h.get('avance'))+'%' if h.get('avance') is not None else 'Sin porcentaje'} · Prueba: {h.get('prueba','Sin registro')}",pequeño))
            if h.get('mensaje'):elementos.append(p(h['mensaje']))
            if corte.get('final'):
                for campo,etiqueta in [('pendiente','Pendientes'),('hallazgos','Hallazgos'),('detalle_prueba','Resultado de prueba')]:
                    if h.get(campo):elementos.append(p(etiqueta+': '+h[campo]))
        for f in imagenes.get(d['id'],[]):
            imagen=Image(BytesIO(f['contenido']));imagen._restrictSize(ancho,240)
            elementos.extend([Spacer(1,6),imagen,p(f"Foto: {f['nombre']} · {f['usuario']} · {_fecha(f['fecha'].isoformat())}",pequeño)])
    elementos.append(p('Bitácora general de las áreas',estilos['Heading2']))
    if not novedades:elementos.append(p('Sin novedades generales registradas.',pequeño))
    for a in novedades:
        elementos.extend([p(f"{a['area']} · {a['categoria']} · {a['estado']}",estilos['Heading3']),p(a['mensaje']),p(f"Autor: {a['nombre']} · {a['usuario']} · Registro: {_fecha(a['fecha'])} · Impacto: {a['impacto']}",pequeño)])
        if a.get('cierre'):elementos.append(p('Cierre informado: '+a['cierre']['mensaje']+' · '+a['cierre']['nombre'],pequeño))
    for entrega in corte.get('entregas',[]):elementos.extend([p(f"Entrega {entrega['fecha']} · {entrega['turno']} · {entrega['nombre']}",estilos['Heading3']),p(entrega.get('comentario') or 'Sin comentarios.'),p(entrega.get('sugerencias') or 'Sin sugerencias.')])
    def pie(canvas,document):
        canvas.setStrokeColor(linea);canvas.line(36,28,A4[0]-36,28);canvas.setFont('Trabajo-Regular',8);canvas.setFillColor(gris);canvas.drawString(36,16,'NeuralMant · Informe de mantenimiento');canvas.drawRightString(A4[0]-36,16,f'Página {document.page}')
    doc.build(elementos,onFirstPage=pie,onLaterPages=pie)
    return out.getvalue()
