import hashlib
import json
import base64
import re
from html import escape
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import uuid4
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd
import streamlit as st
from database import trabajos as db
from database import novedades_area as area_db
from database.usuarios import cargar_centros
from modulos.programacion_pdf import texto_pdf, extraer_trabajos
from reportes.trabajos import generar_pdf
from ia.cliente import mensaje_amigable_ia

COLUMNAS=['ot','descripcion','linea','area','equipo','ejecutor','inicio_plan','fin_plan','referencia_pdf']

def _fecha(v):
    return datetime.fromisoformat(v).replace(tzinfo=ZoneInfo('UTC')).astimezone(ZoneInfo('America/Santiago')).strftime('%d/%m %H:%M') if v else 'Sin actualización'

def _cargar(u):
    if not db.puede_publicar(u):st.error('Solo programadores o administración pueden cargar la programación.');return
    st.subheader('Nuevo programa de fin de semana')
    titulo=st.text_input('Nombre del programa',placeholder='Trabajos fin de semana · Planta San Vicente')
    centros=list(cargar_centros()) if u.get('es_admin') else [str(u.get('centro',''))]
    centro=st.selectbox('Centro',centros)
    hoy=datetime.now(ZoneInfo('America/Santiago')).date()
    a,b=st.columns(2);inicio=a.date_input('Desde',hoy);fin=b.date_input('Hasta',hoy+timedelta(days=2))
    archivo=st.file_uploader('Programación PDF (hasta 10 MB)',type=['pdf'],key='trab_pdf')
    if not archivo:return
    contenido=archivo.getvalue();huella=hashlib.sha256(contenido).hexdigest()
    filas_key='trab_import_'+huella+'_'+centro
    st.session_state.setdefault(filas_key,[])
    if st.button('Extraer trabajos del PDF con GearBot'):
        try:
            with st.spinner('Leyendo la programación…'):
                nuevas=extraer_trabajos(texto_pdf(contenido))
                st.session_state[filas_key]=nuevas
                st.session_state['trab_import_revision_'+huella]=st.session_state.get('trab_import_revision_'+huella,0)+1
            st.success(f'Se extrajeron {len(nuevas)} trabajos. Revisa la tabla antes de publicar.')
        except Exception as exc:
            st.warning(mensaje_amigable_ia(exc) or 'No fue posible extraer los trabajos. Puedes ingresar las filas manualmente o volver a intentar. '+(str(exc) if isinstance(exc,ValueError) else ''))
    with st.expander('Texto del PDF para verificar'):
        try:st.text(texto_pdf(contenido))
        except ValueError as exc:st.warning(str(exc))
    st.caption('Revisa las filas antes de publicar. Área y descripción son obligatorias; línea y equipo son opcionales. Cualquier supervisor o coordinador del centro puede registrar avances.')
    filas=st.data_editor(pd.DataFrame(st.session_state[filas_key],columns=COLUMNAS),num_rows='dynamic',hide_index=True,
        key='trab_editor_'+huella+'_'+centro+'_'+str(st.session_state.get('trab_import_revision_'+huella,0)),column_config={'area':st.column_config.TextColumn('Área',required=True),'descripcion':st.column_config.TextColumn('Descripción',required=True),'linea':st.column_config.TextColumn('Línea (opcional)'),'equipo':st.column_config.TextColumn('Equipo (opcional)')})
    st.caption('Al publicar una programación posterior, se cerrará la anterior de este centro y se conservará solo su PDF final por tres meses. Cargar o extraer el archivo todavía no la cierra.')
    if st.button('Publicar programa revisado y cerrar el anterior',type='primary'):
        try:
            lista=filas.fillna('').to_dict('records')
            n=db.crear_programa(u['correo'],titulo,centro,inicio.isoformat(),fin.isoformat(),archivo.name,contenido,lista)
            st.session_state['trab_programa']=n;st.session_state['trab_abrir_vista']='Tablero';st.session_state['trab_flash']='Programa publicado.';st.rerun()
        except ValueError as exc:st.error(str(exc))

def preparacion_por_area(filas):
    """A finished job alone is never evidence of a successful functional test."""
    resultado=[]
    for area in sorted({d['area'] for d in filas}):
        grupo=[d for d in filas if d['area']==area]
        elegibles=[d for d in grupo if d['estado']=='Terminado' and not d.get('pendiente')]
        resultado.append(dict(area=area,total=len(grupo),probados=sum(d['prueba']=='Aprobada' for d in elegibles),
            sin_prueba=sum(d['prueba']=='No requerida' and bool(d.get('detalle_prueba','').strip()) for d in elegibles)))
    return resultado


def pregunta_bitacora(d):
    from motores.pruebas_trabajos import PREGUNTAS
    paso=(d.get('dialogo_prueba') or {}).get('paso')
    if paso:return PREGUNTAS.get(paso,'Cuéntame qué observaste durante la prueba.')
    if d['estado']=='Terminado':
        if d['prueba'] in ('Aprobada','No requerida') and not d.get('pendiente'):
            return 'Este trabajo está listo según los registros. Puedes agregar una novedad o continuar con otro trabajo del área.'
        return 'La ejecución terminó. ¿Ya se realizaron las pruebas de funcionamiento? Registra también lo que queda pendiente.'
    if d['estado']=='Detenido':return '¿Qué está impidiendo continuar? Cuéntame qué falta para retomar el trabajo.'
    if d['estado']=='Pendiente':return '¿Ya comenzó este trabajo? Cuéntame qué encontraste durante el recorrido.'
    return '¿Qué se ha realizado desde la última revisión? Cuéntame qué falta o si apareció alguna observación.'


ESTADO_VISUAL={'Pendiente':('🟡','Pendiente','#facc15'),'En ejecución':('🟠','En proceso','#fb923c'),
    'Terminado':('🟢','Terminada','#4ade80'),'Detenido':('🔴','Detenida','#f87171')}


def etiqueta_estado(d):
    icono,texto,_=ESTADO_VISUAL.get(d['estado'],('⚪',d['estado'],'#cbd5e1'))
    return icono+' '+texto


def grupos_actividades(filas,pruebas=False):
    if not pruebas:return [('Por completar',[d for d in filas if d['estado']!='Terminado']),('Ejecución terminada',[d for d in filas if d['estado']=='Terminado'])]
    return [('Faltan por probar / en prueba',[d for d in filas if d['prueba'] not in ('Aprobada','Fallida','No requerida')]),
        ('Pruebas fallidas / por resolver',[d for d in filas if d['prueba']=='Fallida']),
        ('Pruebas aprobadas',[d for d in filas if d['prueba']=='Aprobada']),
        ('Prueba no requerida',[d for d in filas if d['prueba']=='No requerida'])]


def _elegir_area_detalle(clave,area):
    st.session_state[clave]=None if st.session_state.get(clave)==area else area


def _detalle_area(u,n,filas,clave,pruebas=False):
    area=st.session_state.get(clave)
    if not area or area not in {d['area'] for d in filas}:return
    grupo=[d for d in filas if d['area']==area]
    with st.container(border=True):
        st.subheader(area+' · '+('Pruebas de funcionamiento' if pruebas else 'Actividades'))
        st.caption('🟡 Pendiente · 🟠 En proceso · 🟢 Terminada · 🔴 Detenida')
        if not pruebas:st.caption('Ejecución terminada no confirma que se hayan aprobado las pruebas.')
        for titulo,actividades in grupos_actividades(grupo,pruebas):
            st.write(f'**{titulo} · {len(actividades)}**')
            if not actividades:st.caption('Sin actividades en este grupo.')
            for d in actividades:
                _,_,color=ESTADO_VISUAL.get(d['estado'],('⚪',d['estado'],'#cbd5e1'))
                st.markdown(f'<div style="border-left:3px solid {color};padding:8px 12px;margin:8px 0"><b>OT {escape(str(d.get("ot") or "#"+str(d["id"])))}</b> · {escape(d["descripcion"])}<br><span style="color:{color}">{escape(etiqueta_estado(d))}</span> · {str(d["avance"])+"%" if d["avance"] is not None else "Sin porcentaje"} · Prueba: {escape(d["prueba"])}</div>',unsafe_allow_html=True)
                if d.get('pendiente'):st.caption('Pendiente: '+d['pendiente'])
                if pruebas and d.get('detalle_prueba'):st.caption(d['detalle_prueba'])
                if db.puede_chat(u) and st.button('Abrir en bitácora',key=f'{clave}_abrir_{d["id"]}'):
                    st.session_state['trab_abrir_vista']='Chat de avance'
                    st.session_state[f'trab_chat_area_{n}']=area
                    st.session_state[f'trab_chat_activo_{n}']=d['id']
                    st.session_state[f'trab_chat_incluir_terminados_{n}']=d['estado']=='Terminado'
                    st.rerun()
        st.button('Cerrar detalle',key=clave+'_cerrar',on_click=_elegir_area_detalle,args=(clave,area))


@st.fragment(run_every='15s')
def _tablero(u,n):
    filas=db.trabajos(u['correo'],n)
    st.caption('Actualización automática cada 15 segundos mientras esta pantalla permanece abierta. Solo se muestran cambios guardados.')
    if not filas:st.info('Sin trabajos.');return
    total=len(filas);valores=[d['avance'] for d in filas if d['avance'] is not None]
    media=round(sum(valores)/len(valores),1) if valores else None
    st.markdown('<div class="trab-dashboard"><span class="trab-eyebrow">CONTROL DE FIN DE SEMANA</span><h2>Estado general de la planta</h2><p>Avance, bloqueos y pruebas de funcionamiento en una sola vista.</p></div>',unsafe_allow_html=True)
    columnas=st.columns(4)
    columnas[0].metric('Avance registrado',str(media)+'%' if media is not None else 'Sin dato')
    columnas[1].metric('Terminados',f"{sum(d['estado']=='Terminado' for d in filas)} / {total}")
    columnas[2].metric('Detenidos',sum(d['estado']=='Detenido' for d in filas))
    columnas[3].metric('Pruebas aprobadas',sum(d['prueba']=='Aprobada' for d in filas))
    st.subheader('Pulso por área')
    tarjetas=st.columns(2)
    for indice,area in enumerate(sorted({d['area'] for d in filas})):
        grupo=[d for d in filas if d['area']==area];valores_area=[d['avance'] for d in grupo if d['avance'] is not None]
        promedio=round(sum(valores_area)/len(valores_area),1) if valores_area else None
        col=tarjetas[indice%2]
        color='#f87171' if any(d['estado']=='Detenido' for d in grupo) else '#ff932b'
        porcentaje=str(promedio)+'%' if promedio is not None else 'Sin porcentaje'
        col.button(f'{area} · {porcentaje} · {sum(d["estado"]=="Terminado" for d in grupo)} / {len(grupo)} terminados',
            key=f'trab_pulso_{n}_{indice}',use_container_width=True,on_click=_elegir_area_detalle,args=(f'trab_detalle_pulso_{n}',area))
        col.progress((promedio or 0)/100)
    _detalle_area(u,n,filas,f'trab_detalle_pulso_{n}')
    st.caption(f"Promedio de los porcentajes registrados, con igual peso por trabajo. {sum(d['avance'] is None for d in filas)} trabajos sin porcentaje.")
    st.subheader('Pruebas de funcionamiento')
    cols=st.columns(2)
    for i,g in enumerate(preparacion_por_area(filas)):
        listo=g['probados']+g['sin_prueba']==g['total']
        adicional=f" · {g['sin_prueba']} sin prueba requerida, documentados" if g['sin_prueba'] else ''
        cols[i%2].button(f'{g["area"]} · {g["probados"]} / {g["total"]} probados y listos',
            key=f'trab_pruebas_area_{n}_{i}',use_container_width=True,on_click=_elegir_area_detalle,args=(f'trab_detalle_pruebas_{n}',g['area']))
        if adicional:cols[i%2].caption(adicional)
    _detalle_area(u,n,filas,f'trab_detalle_pruebas_{n}',pruebas=True)
    st.caption('Cuenta trabajos terminados con prueba aprobada y sin pendientes. Los casos con prueba no requerida se identifican por separado.')
    alertas=[d for d in filas if d['estado']=='Detenido' or d.get('pendiente')]
    if alertas:
        st.subheader('Requiere atención')
        for d in alertas[:5]:st.warning(f"{d['area']} · OT {d.get('ot') or '#'+str(d['id'])}: {d.get('pendiente') or 'Trabajo detenido'}")
        if len(alertas)>5:st.caption(f"Hay {len(alertas)} trabajos con pendientes o bloqueos; consulta el informe para el detalle completo.")
    novedades=area_db.listar(u['correo'],n)
    if novedades:
        with st.expander('Novedades por área · '+str(sum(r['estado']=='Abierto' for r in novedades))+' abiertas'):
            for r in novedades:
                st.write(f"**{r['area']} · {r['categoria']} · {r['estado']}** — {r['mensaje']}")
                st.caption(f"{r['nombre']} · {_fecha(r['fecha'])} · Impacto: {r['impacto']}")
    st.caption('Descarga el informe en Reportes de turno para revisar trabajos, comentarios, responsables de cada registro y evidencias.')


def _actualizar(u,n,ident_fijo=None):
    filas=db.trabajos(u['correo'],n)
    if not filas:st.info('Sin trabajos.');return
    opciones=[d for d in filas if db.puede_actualizar(u,d)]
    if not opciones:st.info('Tu cuenta no puede actualizar este programa. Puedes consultar el tablero.');return
    ident=ident_fijo or st.selectbox('Trabajo para actualizar',[d['id'] for d in opciones],format_func=lambda i:next(f"#{i} · {d['linea']} · {d['descripcion']}" for d in opciones if d['id']==i))
    d=next(x for x in opciones if x['id']==ident)
    st.caption(f"Último registro: {_fecha(d['actualizado'])} · {d['autor'] or 'Sin actualización'}")
    # Retain original version while typing; a concurrent save triggers a conflict instead of overwriting.
    revision_key=f'trab_revision_{n}_{ident}'
    st.session_state.setdefault(revision_key,d['version'])
    if st.button('Recargar datos guardados',key=f'trab_recargar_{ident}'):
        st.session_state[revision_key]=d['version']
        for k in list(st.session_state):
            if str(k).startswith(f'trab_form_{ident}_'):st.session_state.pop(k,None)
        st.rerun()
    pref=f'trab_form_{ident}_' 
    with st.form(pref):
        a,b=st.columns(2)
        estado=a.selectbox('Estado',db.ESTADOS,index=db.ESTADOS.index(d['estado']),key=pref+'estado')
        avance=b.number_input('Avance %',0,100,int(d['avance'] or 0),step=5,key=pref+'avance')
        pendiente=st.text_area('Qué queda pendiente / bloqueos',value=d['pendiente'],key=pref+'pendiente')
        hallazgos=st.text_area('Hallazgos y novedades para el siguiente turno',value=d['hallazgos'],key=pref+'hallazgos')
        prueba=st.selectbox('Prueba de funcionamiento',db.PRUEBAS,index=db.PRUEBAS.index(d['prueba']),key=pref+'prueba')
        detalle=st.text_area('Resultado / evidencia de prueba o motivo de no requerirla',value=d['detalle_prueba'],key=pref+'detalle')
        fotos=st.file_uploader('Fotos opcionales · JPG/PNG · hasta 2 MB cada una · máximo 3 por actualización',type=['jpg','jpeg','png'],accept_multiple_files=True,key=pref+'fotos')
        guardar=st.form_submit_button('Guardar avance',type='primary')
    if guardar:
        try:
            db.actualizar(u['correo'],n,ident,st.session_state[revision_key],dict(estado=estado,avance=int(avance),origen_avance='informado_supervisor',pendiente=pendiente,hallazgos=hallazgos,prueba=prueba,detalle_prueba=detalle),[(f.name,f.getvalue()) for f in fotos])
            st.session_state.pop(revision_key,None)
            st.session_state['trab_limpiar_form']=pref
            st.session_state['trab_flash']='Avance guardado y disponible en el tablero.';st.rerun()
        except ValueError as exc:st.error(str(exc))
    with st.expander('Fotos y bitácora'):
        for f in db.evidencia(u['correo'],n,ident):st.image(f['contenido'],caption=f"{f['nombre']} · {f['usuario']} · {_fecha(f['fecha'].isoformat())}")
        for h in reversed(d['historial']):st.write(f"{_fecha(h['fecha'])} · {h['nombre']} · {h['estado']} · Avance: {str(h['avance'])+'%' if h['avance'] is not None else 'Sin porcentaje'} · Prueba: {h['prueba']}");st.write(h['pendiente']);st.write(h['hallazgos'])


def _plan_etapas(u,n,d):
    from ia.etapas_trabajos import proponer_plan, plan_base
    with st.expander('Revisar etapas y pesos para estimar el avance'):
        clave=f'trab_plan_etapas_{n}_{d["id"]}'
        if st.button('Proponer etapas según el trabajo',key=clave+'_generar'):
            try:st.session_state[clave]=proponer_plan(d['descripcion'])
            except Exception:st.warning('GearBot no pudo proponer etapas. Puedes definirlas manualmente.')
        base=st.session_state.get(clave,d.get('etapas') or plan_base(d['descripcion']))
        plan=st.data_editor(pd.DataFrame(base,columns=['etapa','peso']),num_rows='dynamic',hide_index=True,key=clave+'_editor')
        st.caption('Plan orientativo: pesos enteros que sumen 100 %. No sustituye la pauta de mantenimiento. El cambio de aceite tiene una plantilla base; otros trabajos requieren revisar su plan.')
        if st.button('Guardar plan revisado',key=clave+'_guardar'):
            try:
                db.configurar_etapas(u['correo'],n,d['id'],d['version'],plan.fillna('').to_dict('records'))
                st.session_state['trab_flash']='Etapas revisadas y guardadas.';st.rerun()
            except ValueError as exc:st.error(str(exc))


def _refrescar_chat():
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    contexto=get_script_run_ctx()
    st.rerun(scope='fragment' if contexto and contexto.fragment_ids_this_run else 'app')


def falta_validacion_funcionamiento(d):
    if d.get('estado')!='Terminado':return False
    if (d.get('dialogo_prueba') or {}).get('paso'):return True
    return d.get('prueba')!='Aprobada' and not (d.get('prueba')=='No requerida' and bool(d.get('detalle_prueba','').strip()))


@st.fragment
def _chat(u,n):
    _limpiar_formularios()
    if st.session_state.get('trab_flash'):st.success(st.session_state.pop('trab_flash'))
    if not db.puede_chat(u):
        st.error('Solo supervisores, coordinadores de mantenimiento o administración pueden registrar mensajes.');return
    filas=db.trabajos(u['correo'],n)
    opciones=[d for d in filas if db.puede_actualizar(u,d)]
    if not opciones:
        st.info('No hay trabajos disponibles para actualizar en esta programación.');return
    # Mantener la actividad recién terminada hasta responder la pregunta de pruebas.
    inmediata_key=f'trab_prueba_inmediata_{n}'
    estados_key=f'trab_chat_estados_{n}'
    anteriores=st.session_state.get(estados_key,{})
    seleccionado_antes=st.session_state.get(f'trab_chat_activo_{n}')
    for d in opciones:
        if d['id']==seleccionado_antes and d['id'] in anteriores and anteriores[d['id']]!='Terminado' and d['estado']=='Terminado' and falta_validacion_funcionamiento(d):
            st.session_state[inmediata_key]=d['id']
    st.session_state[estados_key]={d['id']:d['estado'] for d in opciones}
    inmediata=next((d for d in opciones if d['id']==st.session_state.get(inmediata_key)),None)
    if inmediata and not falta_validacion_funcionamiento(inmediata):
        st.session_state.pop(inmediata_key,None);inmediata=None
    pendiente_key=f'trab_chat_pendiente_{n}'
    seleccionado_key=f'trab_chat_activo_{n}'
    area_key=f'trab_chat_area_{n}'
    mensaje=None;fotos=[];version_envio=None
    anterior=st.session_state.get(seleccionado_key)
    if area_key not in st.session_state and anterior:
        anterior_fila=next((d for d in opciones if d['id']==anterior),None)
        if anterior_fila:st.session_state[area_key]=anterior_fila['area']
    def cambiar_area():
        st.session_state.pop(seleccionado_key,None)
        st.session_state.pop(f'trab_chat_incluir_terminados_{n}',None)
        st.session_state.pop(f'trab_chat_solo_validacion_{n}',None)
        st.session_state.pop(inmediata_key,None)
    with st.container(border=True):
        st.markdown('<span class="trab-chat-area-anchor"></span>',unsafe_allow_html=True)
        st.write('**¿A qué área vamos ahora?**')
        areas=sorted({d['area'] for d in opciones})
        if st.session_state.get(area_key) not in [None]+areas:st.session_state.pop(area_key,None)
        area=st.selectbox('Área que estás revisando',[None]+areas,key=area_key,format_func=lambda v:v or 'Elige un área',on_change=cambiar_area)
        if area:st.caption('Área actual: '+area+' · Puedes cambiarla en cualquier momento.')
    if not area:
        with st.chat_message('assistant'):st.write('Elige el área que estás recorriendo y te muestro sus trabajos pendientes.')
        return
    grupo=[d for d in opciones if d['area']==area]
    pendientes=[d for d in grupo if d['estado']!='Terminado']
    with st.chat_message('assistant'):
        st.write(f"Estamos en **{area}**. Hay **{len(pendientes)} trabajos por completar**. ¿Qué trabajo revisamos?")
    st.caption('🟡 Pendiente · 🟠 En proceso · 🟢 Terminada · 🔴 Detenida')
    validaciones=[d for d in grupo if falta_validacion_funcionamiento(d)]
    validacion_key=f'trab_chat_solo_validacion_{n}'
    filtro_activo=bool(st.session_state.get(validacion_key))
    solo_validacion=st.toggle('Solo pendientes de validación de funcionamiento',key=validacion_key,
        disabled=not validaciones and not filtro_activo,help='Trabajos terminados cuya prueba está pendiente, en curso o fallida. Desaparecen al aprobar la prueba o documentar que no la requieren.')
    if validaciones:st.caption(f'{len(validaciones)} trabajos terminados pendientes de validación de funcionamiento en {area}.')
    if len(grupo)>len(pendientes):st.caption(f'{len(grupo)-len(pendientes)} terminados. Puedes revisar sus pruebas o consultar todos los terminados.')
    mostrar_todos=st.checkbox('Mostrar trabajos terminados',key=f'trab_chat_incluir_terminados_{n}',disabled=solo_validacion)
    visibles=validaciones if solo_validacion else (grupo if mostrar_todos else pendientes)
    if inmediata and inmediata['area']==area and inmediata['id'] not in {d['id'] for d in visibles}:visibles=visibles+[inmediata]
    actual=st.session_state.get(seleccionado_key)
    if actual and actual not in {d['id'] for d in visibles}:st.session_state.pop(seleccionado_key,None)
    if not visibles:
        st.success('No quedan trabajos pendientes de validación de funcionamiento en esta área.' if solo_validacion else 'Todas las actividades del área tienen su ejecución terminada. Puedes dejar una novedad del área o activar el filtro de terminados.')
    if st.session_state.get(seleccionado_key) is None:st.session_state[seleccionado_key]=0
    ident=st.selectbox('Actividad o novedad del área',[0]+[d['id'] for d in visibles],key=seleccionado_key,
        format_func=lambda i:'📝 Novedad del área · sin actividad asociada' if i==0 else next(f"OT {d.get('ot') or '#'+str(i)} · {d['descripcion']} · {etiqueta_estado(d)} · {str(d['avance'])+'%' if d['avance'] is not None else 'Sin porcentaje'} · Prueba: {d['prueba']}" for d in visibles if d['id']==i))
    if ident==0:
        _chat_area(u,n,area);return
    if ident is None:return
    d=next(x for x in grupo if x['id']==ident)
    with st.chat_message('assistant'):
        st.write(f"**{area} · {d['descripcion']}**")
        st.caption(f"{etiqueta_estado(d)} · Avance: {str(d['avance'])+'%' if d['avance'] is not None else 'Por estimar'} · Prueba: {d['prueba']}")
        if d.get('pendiente'):st.write('**Pendiente:** '+d['pendiente'])
    _galeria_trabajo(u,n,d)
    st.caption('BITÁCORA DEL TRABAJO · últimos registros')
    for h in [h for h in d['historial'] if not h.get('automatico')][-6:]:
        with st.chat_message('user'):
            st.caption(f"{h['nombre']} · {_fecha(h['fecha'])}")
            st.write(h.get('mensaje') or f"{h['estado']} · Prueba: {h['prueba']}")
    if d['estado']!='Terminado':
        with st.chat_message('assistant'):st.write(pregunta_bitacora(d))
    _pruebas_visibles(u,n,d)
    pendiente=st.session_state.get(pendiente_key)
    if pendiente:
        st.warning('Hay una novedad que no se pudo guardar. Conserva su trabajo original; no se enviará a otra área.')
        st.write(pendiente['mensaje'])
        if pendiente.get('trabajo_id')==ident and st.button('Reintentar guardar en este trabajo'):
            mensaje=pendiente['mensaje'];fotos=pendiente['fotos'];version_envio=d['version']
        if st.button('Descartar novedad sin guardar'):
            st.session_state.pop(pendiente_key,None);_refrescar_chat()
    with st.expander('Adjuntar fotos (opcional)'):
        adjuntos=st.file_uploader('Máximo 3 JPG/PNG de hasta 2 MB',type=['jpg','jpeg','png'],accept_multiple_files=True,key=f'trab_chat_adjuntos_{n}_{ident}')
        if adjuntos:st.caption(f'{len(adjuntos)} foto(s) seleccionadas. Se guardan al enviar el comentario.')
    escrito=st.chat_input('Escribe tu observación o responde a GearBot…',key=f'trab_chat_entrada_{n}_{ident}',disabled=bool(pendiente))
    if escrito:
        if len(escrito)>10000 or len(adjuntos or [])>3 or any(f.size>2*1024*1024 for f in adjuntos or []):
            st.error('Máximo 10.000 caracteres y 3 fotos de hasta 2 MB.');return
        mensaje=escrito;fotos=[(f.name,f.getvalue()) for f in adjuntos or []];version_envio=d['version']
        st.session_state[pendiente_key]=dict(trabajo_id=ident,mensaje=mensaje,fotos=fotos)
    if mensaje:
        with st.chat_message('user'):
            st.write(mensaje)
            st.caption('Guardando novedad…')
        from ia.novedad_automatica import directo, combinar
        from ia.cola_novedades import iniciar
        cambio={k:d[k] for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba')}
        from motores.pruebas_trabajos import desde_mensaje
        respuesta=desde_mensaje(d,mensaje)
        inmediato=respuesta or directo(mensaje)
        if respuesta:cambio=respuesta
        elif inmediato:cambio=combinar(d,inmediato)
        try:
            version=db.actualizar(u['correo'],n,ident,version_envio,cambio,fotos,mensaje=mensaje)
            st.session_state.pop(pendiente_key,None)
            if respuesta and (respuesta.get('dialogo_prueba') or {}).get('postergada'):
                st.session_state.pop(inmediata_key,None)
                st.session_state['trab_limpiar_seleccion']=f'trab_chat_activo_{n}'
            if inmediato:
                db.descartar_novedades_anteriores(u['correo'],n,ident)
                st.session_state['trab_flash']='Novedad y avance guardados.'
            else:
                try:
                    db.encolar_novedad(u['correo'],n,ident,version,mensaje);iniciar()
                    st.session_state['trab_flash']='Novedad guardada. GearBot está actualizando el avance; puedes seguir recorriendo la planta.'
                except ValueError as exc:st.session_state['trab_flash']=str(exc)
            if fotos:st.session_state['trab_flash']+=f' {len(fotos)} foto(s) guardadas correctamente.'
            st.session_state.pop(f'trab_revision_{n}_{ident}',None)
            st.session_state['trab_limpiar_form']=[f'trab_chat_adjuntos_{n}_{ident}',f'trab_form_{ident}_']
            _refrescar_chat()
        except ValueError as exc:st.error(str(exc))
    _estado_novedad(u,n,ident)
    a,b=st.columns(2)
    acciones=[] if d['estado']=='Terminado' else ([(a,'Iniciado')] if d['estado']=='Pendiente' else [])+[(b,'Trabajo terminado')]
    for col,accion in acciones:
        if col.button(accion,key=f'trab_chat_rapido_{ident}_{accion}'):
            cambio={k:d[k] for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba')}
            cambio['estado']='En ejecución' if accion=='Iniciado' else 'Terminado'
            cambio['avance']=None if accion=='Iniciado' else 100
            cambio['origen_avance']='estado_supervisor'
            try:
                db.actualizar(u['correo'],n,ident,d['version'],cambio,mensaje=accion+' registrado por el responsable de turno.')
                st.session_state.pop(f'trab_revision_{n}_{ident}',None);st.session_state['trab_limpiar_form']=f'trab_form_{ident}_';_refrescar_chat()
            except ValueError as exc:st.error(str(exc))
    with st.expander('Ver bitácora completa o corregir un registro'):
        if st.toggle('Abrir herramientas de corrección',key=f'trab_chat_detalle_{n}_{ident}'):
            _actualizar(u,n,ident)
            if db.gestor(u):_plan_etapas(u,n,d)



def _galeria_trabajo(u,n,d):
    registradas=len(d.get('fotos',[]))
    if not registradas:
        st.caption('Fotos guardadas en esta actividad: 0');return
    try:fotos=db.evidencia(u['correo'],n,d['id'])
    except (ValueError,SQLAlchemyError):
        st.warning('No se pudieron comprobar las fotos guardadas. Intenta volver a abrir la actividad.');return
    st.caption(f'Fotos guardadas en esta actividad: {len(fotos)}')
    if len(fotos)!=registradas:st.warning(f'El trabajo registra {registradas} fotos y se recuperaron {len(fotos)}. Revisa los adjuntos antes de cerrar el programa.')
    with st.expander(f'Ver fotos guardadas ({len(fotos)})'):
        columnas=st.columns(3)
        for i,f in enumerate(fotos):
            fecha=f.get('fecha');fecha=fecha.isoformat() if hasattr(fecha,'isoformat') else fecha
            columnas[i%3].image(f['contenido'],caption=f['nombre']+' · '+str(f.get('usuario',''))+' · '+_fecha(fecha),width='stretch')


def _galeria_area(registros):
    fotos=[(r,f) for r in registros for f in r.get('fotos',[])]
    st.caption(f'Fotos guardadas en las novedades de esta área: {len(fotos)}')
    if fotos:
        with st.expander(f'Ver todas las fotos del área ({len(fotos)})'):
            columnas=st.columns(3)
            for i,(r,f) in enumerate(fotos):
                columnas[i%3].image(base64.b64decode(f['contenido']),caption=f['nombre']+' · '+r['nombre']+' · '+_fecha(r['fecha']),width='stretch')


def _chat_area(u,n,area):
    from motores.foco_partida import CATEGORIAS
    pref=f'trab_area_{n}_{area}_'
    registros=area_db.listar(u['correo'],n,area)
    st.write('**Novedades de '+area+'**')
    st.caption('Seguridad, calidad, trabajos no informados o cualquier observación del área. No cambia el avance de las actividades.')
    _galeria_area(registros)
    for r in registros[-8:]:
        with st.chat_message('user'):
            st.caption(f"{r['nombre']} · {_fecha(r['fecha'])} · {r['categoria']} · {r['estado']}")
            st.write(r['mensaje'])
            if r.get('fotos'):st.caption(f"{len(r['fotos'])} foto(s) guardadas con esta novedad. Puedes verlas en la galería del área.")
            if r.get('cierre'):st.caption('Resolución: '+r['cierre']['mensaje'])
    categoria=st.selectbox('Tipo de novedad',[c for c in CATEGORIAS if c!='Automática'],index=5,key=pref+'categoria')
    st.caption('Explica en el comentario lo observado, sus consecuencias y lo que falta por resolver, si corresponde.')
    revision=st.session_state.get(pref+'revision_fotos',0)
    fotos=st.file_uploader('Imágenes de la novedad (opcional, máximo 3 de 2 MB)',type=['jpg','jpeg','png'],accept_multiple_files=True,key=pref+'fotos_'+str(revision))
    if fotos:st.caption(f'{len(fotos)} imagen(es) seleccionadas. Se guardan al enviar la novedad.')
    pend=st.session_state.get(pref+'pendiente')
    escrito=st.chat_input('¿Qué observaste en '+area+'?',key=pref+'mensaje',disabled=bool(pend),max_chars=10000)
    guardar=None
    if escrito:
        guardar=dict(mensaje=escrito,clave=str(uuid4()),categoria=categoria,fotos=[(f.name,f.getvalue()) for f in fotos],capturado=datetime.utcnow().isoformat()+'Z')
        st.session_state[pref+'pendiente']=guardar
    if pend:
        st.warning('Esta novedad todavía no se guardó. Conserva su área original.')
        st.write(pend['mensaje'])
        if st.button('Reintentar novedad del área',key=pref+'reintentar'):guardar=pend
    if guardar:
        try:
            area_db.guardar(u['correo'],n,area,**guardar)
            st.session_state.pop(pref+'pendiente',None)
            st.session_state[pref+'revision_fotos']=revision+1
            st.session_state['trab_flash']='Novedad del área guardada y disponible para el informe.'+(f" {len(guardar.get('fotos',[]))} foto(s) guardadas correctamente." if guardar.get('fotos') else '');_refrescar_chat()
        except ValueError as exc:st.error(str(exc))
        except SQLAlchemyError:st.error('No se pudo guardar ahora. La novedad se conserva para reintentar.')
    abiertos=[r for r in registros if r['estado']=='Abierto' and not r.get('resuelve')]
    if abiertos:
        with st.expander(f'Seguimiento de hallazgos abiertos ({len(abiertos)})'):
            resolver=st.selectbox('Hallazgo a resolver',[None]+[r['id'] for r in abiertos],format_func=lambda i:'Elige el hallazgo' if i is None else next(r['mensaje'][:100] for r in abiertos if r['id']==i),key=pref+'resolver')
            texto=st.text_area('Qué se corrigió o verificó',key=pref+'resolucion')
            if st.button('Registrar resolución',key=pref+'cerrar'):
                if not resolver or not texto.strip():st.warning('Elige el hallazgo y describe qué se corrigió.')
                else:
                    clave_key=pref+'clave_cierre_'+hashlib.sha256((str(resolver)+':'+texto).encode()).hexdigest()
                    st.session_state.setdefault(clave_key,str(uuid4()))
                    try:
                        area_db.guardar(u['correo'],n,area,texto,st.session_state[clave_key],resuelve=resolver)
                        st.session_state.pop(clave_key,None)
                        st.session_state['trab_limpiar_form']=[pref+'resolver',pref+'resolucion']
                        st.session_state['trab_flash']='Resolución registrada con autor y fecha.';_refrescar_chat()
                    except ValueError as exc:st.error(str(exc))


def _pruebas_visibles(u,n,d):
    from motores.pruebas_trabajos import PREGUNTAS
    if d['estado']!='Terminado':return
    with st.container(border=True):
        st.subheader('Prueba de funcionamiento: '+d['prueba'])
        paso=(d.get('dialogo_prueba') or {}).get('paso')
        if paso:
            with st.chat_message('assistant'):st.write(PREGUNTAS.get(paso,'Cuéntame cómo resultó la prueba.'))
        elif d['prueba'] not in ('Aprobada','No requerida'):st.write('¿Se realizaron las pruebas de funcionamiento?' if d['prueba']!='Fallida' else '¿Se repitieron las pruebas de funcionamiento?')
        acciones=[]
        if paso in (None,'','realizacion') and d['prueba'] not in ('Aprobada','No requerida'):acciones=[('Sí, se realizaron','iniciar_prueba'),('Aún no','posponer_prueba')]
        elif paso=='observaciones':acciones=[('Funcionamiento normal, sin observaciones','sin_observaciones'),('Hubo observaciones','con_observaciones')]
        elif paso=='impacto':acciones=[('Sí, impide la partida','impide_partida'),('No, funcionamiento normal','no_impide_partida')]
        for etiqueta,accion in acciones:
            if st.button(etiqueta,key=f'trab_prueba_{n}_{d["id"]}_{accion}',type='primary'):
                try:
                    db.registrar_prueba(u['correo'],n,d['id'],d['version'],accion)
                    db.descartar_novedades_anteriores(u['correo'],n,d['id'])
                    if accion=='posponer_prueba':
                        st.session_state.pop(f'trab_prueba_inmediata_{n}',None)
                        st.session_state['trab_limpiar_seleccion']=f'trab_chat_activo_{n}'
                        st.session_state['trab_flash']='Trabajo terminado. Las pruebas quedan pendientes; puedes continuar con otra actividad.'
                    else:st.session_state['trab_flash']='Resultado de prueba registrado.'
                    _refrescar_chat()
                except ValueError as exc:st.error(str(exc))
        if d.get('detalle_prueba'):st.caption(d['detalle_prueba'])


@st.fragment(run_every='2s')
def _estado_novedad(u,n,ident):
    ultima=db.ultima_novedad(u['correo'],n,ident)
    if not ultima:return
    if ultima['estado'] in ('pendiente','procesando'):
        st.caption('✓ Mensaje guardado · GearBot actualiza el avance en segundo plano…')
    elif ultima['estado']=='pregunta':
        with st.chat_message('assistant'):st.write(ultima['detalle']+' Responde aquí en el chat.')
    elif ultima['estado']=='error':st.warning(ultima['detalle'])
    elif ultima['estado']=='lista':
        st.caption('✓ '+ultima['detalle'])
        clave=f'trab_ia_vista_{n}_{ident}'
        if st.session_state.get(clave)!=ultima['id']:
            st.session_state[clave]=ultima['id'];st.rerun(scope='app')


def _reportes(u,p):
    from ia.resumen_turno import resumen_base, mejorar_resumen
    n=p['id'];ahora=datetime.now(ZoneInfo('America/Santiago'));fecha=ahora.date().isoformat()
    turno='Día' if 7<=ahora.hour<19 else 'Noche'
    filas=db.trabajos(u['correo'],n)
    st.subheader('Informe ejecutivo de ejecución y partida')
    st.caption('Resumen de lo registrado en el programa hasta ahora. Puedes ajustar el texto antes de descargar; los estados y porcentajes del trabajo se conservan.')
    novedades=area_db.listar(u['correo'],n)
    total_fotos=sum(len(d.get('fotos',[])) for d in filas)+sum(len(a.get('fotos',[])) for a in novedades)
    st.caption(f'Fotos registradas para este informe: {total_fotos}. El PDF incluye todas las fotos recuperadas de este corte.')
    base=resumen_base(filas,novedades);pref=f'trab_resumen_{n}_'
    firma=hashlib.sha256(json.dumps(dict(trabajos=filas,novedades=[{k:v for k,v in a.items() if k!='fotos'} for a in novedades]),ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    previo=st.session_state.get(pref+'base')
    if previo is None or all(st.session_state.get(pref+k)==previo[k] for k in ('comentario','sugerencias')):
        for k in ('comentario','sugerencias'):st.session_state[pref+k]=base[k]
        st.session_state[pref+'fuente']=firma;st.session_state[pref+'base']=base
    if st.session_state.get(pref+'fuente')!=firma:
        st.info('Hay nuevas novedades en la bitácora. Actualiza el resumen desde el chat o revísalo con GearBot antes de descargar.')
    a,b=st.columns(2)
    if a.button('Actualizar resumen desde el chat'):
        st.session_state[pref+'comentario']=base['comentario'];st.session_state[pref+'sugerencias']=base['sugerencias'];st.session_state[pref+'fuente']=firma;st.session_state[pref+'base']=base
    if b.button('Analizar y sintetizar con GearBot'):
        try:
            with st.spinner('GearBot analiza los registros y prepara la conclusión. Las bitácoras extensas se revisan en partes…'):
                nuevo=mejorar_resumen(filas,{k:st.session_state[pref+k] for k in ('comentario','sugerencias')},novedades)
            st.session_state[pref+'comentario']=nuevo['comentario'];st.session_state[pref+'sugerencias']=nuevo['sugerencias'];st.session_state[pref+'fuente']=firma;st.session_state[pref+'base']=base
            st.session_state.pop(pref+'error_ia',None)
            st.success('Redacción ajustada. Revisa el resumen antes de descargar.')
        except Exception as exc:
            from ia.diagnostico import diagnosticar_resumen
            st.session_state[pref+'error_ia']=diagnosticar_resumen(exc)
    error_ia=st.session_state.get(pref+'error_ia')
    if error_ia:
        st.warning(error_ia['mensaje']+' Tu resumen se conserva y puedes descargarlo. Referencia: '+error_ia['referencia'])
        if u.get('es_admin'):
            with st.expander('Ver detalle del error de GearBot',expanded=True):
                st.code('Referencia: '+error_ia['referencia']+'\nFecha UTC: '+error_ia['fecha']+'\nTipo: '+error_ia['tipo']+'\nModelo: '+error_ia['modelo']+'\nDetalle: '+error_ia['detalle'],language='text')
                st.caption('Puedes copiar este detalle para revisar la causa. La clave de la API se oculta.')
    comentario=st.text_area('Resumen ejecutivo',key=pref+'comentario',height=240)
    sugerencias=st.text_area('Acciones y focos de seguimiento',key=pref+'sugerencias',height=120)
    actual=dict(titulo=p['titulo'],centro=p['centro'],fecha=fecha,turno=turno,comentario=comentario,sugerencias=sugerencias,autor=u['correo'],nombre=u['nombre'],generado=datetime.utcnow().isoformat(),trabajos=filas,lineas=db.lineas(filas),novedades_area=novedades,sugerencias_automaticas=sugerencias==base['sugerencias'])
    pdf=generar_pdf(u['correo'],n,actual,True)
    def registrar_descarga():
        if db.puede_chat(u) and (comentario!=base['comentario'] or sugerencias!=base['sugerencias']):
            try:
                anteriores=db.cierres(u['correo'],n)
                if not anteriores or anteriores[0].get('comentario')!=comentario or anteriores[0].get('sugerencias')!=sugerencias:
                    db.cerrar_turno(u['correo'],n,fecha,turno,comentario,str(uuid4()),sugerencias=sugerencias)
            except ValueError as exc:st.session_state['trab_flash']='No se guardaron las notas: '+str(exc)
    st.download_button('Descargar informe PDF',pdf,file_name=f'Informe_turno_{n}_{fecha}.pdf',mime='application/pdf',type='primary',on_click=registrar_descarga)
    st.caption('Descargar no cierra la semana. El cierre ocurre al publicar la programación siguiente.')


def _limpiar_formularios():
    seleccion=st.session_state.pop('trab_limpiar_seleccion',None)
    if seleccion:st.session_state.pop(seleccion,None)
    limpiar=st.session_state.pop('trab_limpiar_form',None)
    if limpiar:
        for k in list(st.session_state):
            if str(k).startswith(tuple(limpiar) if isinstance(limpiar,list) else limpiar):st.session_state.pop(k,None)


def mostrar_trabajos():
    _limpiar_formularios()
    destino=st.session_state.pop('trab_abrir_vista',None)
    if destino:st.session_state['trab_vista']=destino
    u=st.session_state.get('usuario_actual') or {}
    if not u.get('correo'):st.error('Inicia sesión.');return
    st.title('Seguimiento de trabajos')
    st.caption('Programación de fin de semana · Avance por turno · Pruebas de funcionamiento')
    if st.session_state.get('trab_flash'):st.success(st.session_state.pop('trab_flash'))
    vistas=['Tablero','Reportes de turno']
    if db.puede_chat(u):vistas.insert(1,'Chat de avance')
    if db.puede_publicar(u):vistas.append('Cargar programación')
    if st.session_state.get('trab_vista') not in vistas:st.session_state.pop('trab_vista',None)
    vista=st.radio('Vista',vistas,horizontal=True,key='trab_vista')
    if vista=='Cargar programación':_cargar(u);return
    planes=db.programas(u['correo'])
    if not planes:st.info('No hay programaciones publicadas para tu centro. Administración puede cargar el PDF y revisar sus trabajos.');return
    ids=[p['id'] for p in planes]
    if st.session_state.get('trab_programa') not in ids:st.session_state.pop('trab_programa',None)
    n=st.selectbox('Programación',ids,key='trab_programa',format_func=lambda i:next(f"{p['titulo']} · {p['inicio']} a {p['fin']} · {'Cerrado' if p.get('cerrado') else 'Vigente'}" for p in planes if p['id']==i))
    p=next(x for x in planes if x['id']==n)
    if p.get('cerrado'):
        st.info('Programa cerrado: solo consulta. Se conserva únicamente el informe final PDF durante tres meses.')
        st.caption('Disponible hasta: '+p.get('vence','')[:10])
        pdf=db.historico_pdf(u['correo'],n)
        st.download_button('Consultar / descargar informe final PDF',pdf,file_name=f'Informe_final_{n}.pdf',mime='application/pdf')
        return
    if vista=='Tablero':
        with st.expander('Programación original'):
            st.download_button('Descargar PDF original',db.fuente(u['correo'],n),file_name='Programacion_original.pdf',mime='application/pdf')
    if vista=='Tablero':_tablero(u,n)
    elif vista=='Chat de avance':_chat(u,n)
    else:_reportes(u,p)
