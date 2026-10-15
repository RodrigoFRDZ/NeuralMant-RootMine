from io import BytesIO
from pathlib import Path
from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY,TA_LEFT
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak,CondPageBreak
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
            if permitidas:imagenes[d['id']]=[f for f in db.evidencia(correo,programa,d['id']) if f['id'] in permitidas]
    return render_pdf(corte,imagenes)

def render_pdf(corte,imagenes=None):
    import base64
    from reportlab.platypus import KeepTogether
    from ia.resumen_turno import resumen_base
    imagenes=imagenes or {};filas=corte['trabajos'];novedades=corte.get('novedades_area',[])
    analisis=focos(filas,novedades)
    fuentes=Path(__file__).resolve().parents[1]/'assets/fonts'
    if 'Trabajo-Regular' not in pdfmetrics.getRegisteredFontNames():
        for tipo,archivo in [('Regular','Reporte-Regular.ttf'),('Bold','Reporte-Bold.ttf')]:
            pdfmetrics.registerFont(TTFont('Trabajo-'+tipo,str(fuentes/archivo)))
    tinta=colors.HexColor('#003087');naranja=colors.HexColor('#E87722');marfil=colors.HexColor('#FFF6E6')
    estilos=getSampleStyleSheet()
    for estilo in estilos.byName.values():
        estilo.textColor=tinta;estilo.fontName='Trabajo-Bold' if estilo.name.startswith(('Heading','Title')) else 'Trabajo-Regular'
    estilos['Title'].fontSize=23;estilos['Title'].leading=28;estilos['Title'].alignment=0
    estilos['Heading2'].fontSize=12;estilos['Heading2'].leading=16;estilos['Heading2'].spaceBefore=16;estilos['Heading2'].spaceAfter=8
    estilos['Heading2'].keepWithNext=True
    estilos['Heading2'].allowWidows=0;estilos['Heading2'].allowOrphans=0
    normal=estilos['BodyText'];normal.fontSize=9;normal.leading=13
    normal.alignment=TA_JUSTIFY;normal.spaceAfter=7
    normal.allowWidows=0;normal.allowOrphans=0;normal.justifyBreaks=0;normal.splitLongWords=1
    nota=ParagraphStyle('Nota',parent=normal,fontSize=8,leading=11,spaceAfter=5,alignment=TA_JUSTIFY)
    celda=ParagraphStyle('Celda',parent=nota,alignment=TA_LEFT,spaceAfter=0)
    metadato=ParagraphStyle('Metadato',parent=nota,alignment=TA_LEFT)
    etiqueta=ParagraphStyle('Etiqueta',parent=normal,fontName='Trabajo-Bold',fontSize=8,leading=11,alignment=TA_LEFT)
    blanco=ParagraphStyle('Blanco',parent=etiqueta,textColor=marfil)
    dato=ParagraphStyle('Indicador',parent=normal,fontName='Trabajo-Bold',fontSize=20,leading=25,alignment=TA_LEFT)
    def p(texto,estilo=normal):return Paragraph(escape(str(texto or '')).replace('\n','<br/>'),estilo)
    def completo(texto):return ' '.join(str(texto or '').split())
    def parrafos(texto):
        return [p(linea.strip()) for linea in str(texto or '').split('\n') if linea.strip()]
    out=BytesIO();ancho=A4[0]-84
    doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=36,leftMargin=36,topMargin=36,bottomMargin=40,title='NeuralMant - Informe ejecutivo de mantenimiento',author='NeuralMant',subject=corte['titulo'])
    elementos=[p('NEURALMANT / MANTENIMIENTO',etiqueta),Spacer(1,10),p('Ejecución y preparación de partida',estilos['Title']),p(corte['titulo'],estilos['Heading2']),
        p(f"Centro {corte['centro']} · {corte['fecha']} · Turno {corte['turno']}",nota),p(f"Corte: {_fecha(corte['generado'])} (Chile) · Preparado por {corte['nombre']}",nota),Spacer(1,10)]
    abiertos=[a for a in novedades if a.get('estado')=='Abierto' and not a.get('resuelve')]
    def listo(d):return d['estado']=='Terminado' and not d.get('pendiente') and (d['prueba']=='Aprobada' or (d['prueba']=='No requerida' and bool(d.get('detalle_prueba','').strip())))
    indicadores=[(f"{sum(d['estado']=='Terminado' for d in filas)} / {len(filas)}",'Actividades terminadas'),(str(sum(listo(d) for d in filas)),'Terminadas y verificadas'),(str(sum(d['estado']=='Detenido' for d in filas)),'Trabajos detenidos'),(str(len(abiertos)),'Novedades abiertas')]
    tabla=Table([[[p(v,dato),p(t,metadato)] for v,t in indicadores]],colWidths=[ancho/4]*4)
    tabla.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),marfil),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]));elementos.append(tabla)
    elementos.append(p('01 / Conclusión ejecutiva',estilos['Heading2']))
    elementos.extend(parrafos(corte.get('comentario') or resumen_base(filas,novedades)['comentario']))
    elementos.append(p('“Terminadas y verificadas”: sin pendientes informados y con prueba aprobada o exclusión justificada. No constituye autorización de partida.',nota))
    def tabla_datos(headers,rows,widths):
        datos=[[p(h,blanco) for h in headers]]+[[p(v,celda) for v in row] for row in rows]
        t=Table(datos,colWidths=[ancho*w for w in widths],repeatRows=1,hAlign='LEFT',splitInRow=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),tinta),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,marfil]),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8)]))
        t.wrap(ancho,100000)
        espacio_fila=doc.height-12-t._rowHeights[0]
        t.splitInRow=int(any(h>espacio_fila for h in t._rowHeights[1:]))
        elementos.append(t)
    elementos.append(p('02 / Estado de entrega por área',estilos['Heading2']))
    rows=[]
    for area in sorted({d['area'] for d in filas}|{a['area'] for a in novedades}):
        grupo=[d for d in filas if d['area']==area]
        terminados=sum(d['estado']=='Terminado' for d in grupo)
        revisiones=sum(d['estado']=='Terminado' and not listo(d) for d in grupo)
        obs=sum(a['area']==area for a in abiertos)
        rows.append([area,f'{terminados}/{len(grupo)}',str(sum(listo(d) for d in grupo)),str(revisiones),str(obs)])
    tabla_datos(['Área','Terminadas / total','Verificadas','Terminadas por revisar','Novedades abiertas'],rows or [['Sin actividades','0/0','0','0','0']],[.28,.18,.17,.19,.18])
    elementos.append(p('Actividades del programa',estilos['Heading2']))
    actividad_rows=[]
    for d in filas:
        avance=str(d['avance'])+'%' if d.get('avance') is not None else 'Sin porcentaje'
        if d.get('origen_avance')=='estimado_etapas':avance+=' (estimado)'
        actividad_rows.append([d['descripcion']+'\n'+d['area'],d['estado']+'\n'+avance,d['prueba']+('\n'+completo(d.get('detalle_prueba')) if d.get('detalle_prueba') else '')])
    if actividad_rows:tabla_datos(['Actividad / área','Estado / avance','Prueba informada'],actividad_rows,[.49,.22,.29])
    elementos.append(p('03 / Prioridades y acciones propuestas',estilos['Heading2']))
    rows=[];vistos=set()
    for etiqueta_foco,clave in [('Antes de partida','partida'),('Retraso informado','retrasos'),('Seguimiento semanal','semana')]:
        for f in analisis[clave]:
            firma=(etiqueta_foco,f['referencia'],f['detalle'])
            if firma in vistos:continue
            vistos.add(firma)
            rows.append([etiqueta_foco+'\n'+f['referencia'],completo(f['detalle']),completo(f['accion'])])
    if rows:tabla_datos(['Foco / actividad o área','Antecedente relevante','Acción propuesta'],rows,[.29,.40,.31])
    else:elementos.append(p('No se identifican focos específicos en lo informado. Confirmar condiciones en terreno.',nota))
    elementos.append(p('Los antecedentes históricos requieren confirmar su vigencia. Las propuestas no asignan responsables ni plazos que no hayan sido informados. Un comentario escrito tarde no demuestra una entrega tardía.',nota))
    elementos.append(p('04 / Novedades de las áreas',estilos['Heading2']))
    # One concise entry per observation; resolutions are attached to the original.
    rows=[]
    for a in novedades:
        if a.get('resuelve'):continue
        tratamiento='Pendiente de resolución informada.'
        if a.get('cierre'):tratamiento='Resolución: '+completo(a['cierre']['mensaje'])
        rows.append([a['area']+'\n'+a['categoria']+' · '+a['estado'],completo(a['mensaje']),tratamiento+'\n'+a['nombre']+' · '+_fecha(a['fecha'])])
    if rows:tabla_datos(['Área / tipo / estado','Antecedente relevante','Tratamiento / trazabilidad'],rows,[.25,.43,.32])
    else:elementos.append(p('Sin novedades generales registradas.',nota))
    if corte.get('sugerencias') and not corte.get('sugerencias_automaticas'):
        elementos.append(p('Indicaciones adicionales de la entrega',estilos['Heading2']))
        elementos.extend(parrafos(corte['sugerencias']))
    # Todas las fotos recuperadas, con su actividad/novedad de origen.
    seleccion=[]
    esperadas=sum(len(a.get('fotos',[])) for a in novedades)+sum(len(d.get('fotos',[])) for d in filas)
    for a in sorted([a for a in novedades if a.get('fotos')],key=lambda a:a.get('estado')!='Abierto'):
        for f in a['fotos']:
            seleccion.append((base64.b64decode(f['contenido']),a['area']+' · '+a['categoria']+' · '+a['estado'],completo(a['mensaje']),f.get('nombre','Imagen')+' · '+a['nombre']+' · '+_fecha(a['fecha'])))
    for d in filas:
        for f in imagenes.get(d.get('id'),[]):
            fecha=f.get('fecha')
            seleccion.append((f['contenido'],d['descripcion']+' · '+d['area'],f"{d['estado']} · Prueba: {d['prueba']}",str(f.get('nombre','Imagen'))+' · '+str(f.get('usuario',''))+' · '+_fecha(fecha.isoformat() if hasattr(fecha,'isoformat') else fecha)))
    if seleccion:
        conteo=f'Se incluyen {len(seleccion)} de {max(esperadas,len(seleccion))} imágenes registradas en este corte.'
        if len(seleccion)<esperadas:conteo+=' Atención: faltan imágenes por recuperar; revisar los adjuntos del programa.'
        cabecera_fotos=[p('05 / Evidencia fotográfica',estilos['Heading2']),p(conteo,nota)]
        for i,(contenido,titulo,contexto,autor) in enumerate(seleccion):
            titulo=f'Foto {i+1} de {len(seleccion)} · '+titulo
            im=Image(BytesIO(contenido));im._restrictSize(ancho,210);im.hAlign='LEFT'
            cabecera=(cabecera_fotos if i==0 else [])+[p(titulo,etiqueta),p(autor,metadato),Spacer(1,6),im,Spacer(1,5)]
            leyenda=p(contexto,nota)
            alto=sum(f.wrap(ancho,100000)[1]+f.getSpaceBefore()+f.getSpaceAfter() for f in cabecera)
            inicio_leyenda=min(leyenda.wrap(ancho,100000)[1],nota.leading*3)
            elementos.append(CondPageBreak(min(alto+inicio_leyenda+8,doc.height-20)))
            elementos.append(KeepTogether(cabecera))
            elementos.extend([leyenda,Spacer(1,12)])
    else:elementos.extend([p('05 / Evidencia fotográfica',estilos['Heading2']),p(f'No se recuperaron las {esperadas} imágenes registradas. Revisar los adjuntos del programa.' if esperadas else 'No hay imágenes adjuntas disponibles para este corte.',nota)])
    def pie(canvas,document):
        canvas.setStrokeColor(naranja);canvas.setLineWidth(.5);canvas.line(36,28,A4[0]-36,28)
        canvas.setFont('Trabajo-Regular',8);canvas.setFillColor(tinta);canvas.drawString(36,16,'NeuralMant · Informe ejecutivo de mantenimiento');canvas.drawRightString(A4[0]-36,16,f'Página {document.page}')
    # Reserva espacio para el título y el inicio real del bloque siguiente.
    # Las tablas extensas siguen paginándose y repitiendo su cabecera.
    ordenados=[]
    for i,elemento in enumerate(elementos):
        if isinstance(elemento,Paragraph) and elemento.style.name=='Heading2' and i+1<len(elementos):
            siguiente=elementos[i+1]
            alto_titulo=elemento.wrap(ancho,100000)[1]+elemento.getSpaceBefore()+elemento.getSpaceAfter()
            if isinstance(siguiente,Table):
                elemento.keepWithNext=False
                siguiente.wrap(ancho,100000)
                comienzo=min(sum(siguiente._rowHeights[:2]),doc.height*.6)
            elif isinstance(siguiente,Paragraph):
                comienzo=min(siguiente.wrap(ancho,100000)[1],siguiente.style.leading*3)+siguiente.getSpaceBefore()
            else:comienzo=45
            ordenados.append(CondPageBreak(alto_titulo+comienzo+8))
        ordenados.append(elemento)
    doc.build(ordenados,onFirstPage=pie,onLaterPages=pie)
    return out.getvalue()
