import hashlib
import re
from html import escape
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import uuid4
import pandas as pd
import streamlit as st
from database import trabajos as db
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

@st.fragment(run_every='15s')
def _tablero(u,n):
    filas=db.trabajos(u['correo'],n)
    st.caption('Actualización automática cada 15 segundos mientras esta pantalla permanece abierta. Solo se muestran cambios guardados.')
    if not filas:st.info('Sin trabajos.');return
    total=len(filas);valores=[d['avance'] for d in filas if d['avance'] is not None]
    media=round(sum(valores)/len(valores),1) if valores else None
    st.markdown('<div class="trab-dashboard"><span class="trab-eyebrow">CONTROL DE FIN DE SEMANA</span><h2>Estado general de la planta</h2><p>Avance, bloqueos y preparación para la partida en una sola vista.</p></div>',unsafe_allow_html=True)
    columnas=st.columns(4)
    columnas[0].metric('Avance registrado',str(media)+'%' if media is not None else 'Sin dato')
    columnas[1].metric('Terminados',f"{sum(d['estado']=='Terminado' for d in filas)} / {total}")
    columnas[2].metric('Detenidos',sum(d['estado']=='Detenido' for d in filas))
    columnas[3].metric('Pruebas aprobadas',sum(d['prueba']=='Aprobada' for d in filas))
    st.subheader('Pulso por área')
    grafico=[];tarjetas=st.columns(2)
    for indice,area in enumerate(sorted({d['area'] for d in filas})):
        grupo=[d for d in filas if d['area']==area];valores_area=[d['avance'] for d in grupo if d['avance'] is not None]
        promedio=round(sum(valores_area)/len(valores_area),1) if valores_area else None
        grafico.append({'Área':area,'Avance %':promedio})
        col=tarjetas[indice%2]
        color='#f87171' if any(d['estado']=='Detenido' for d in grupo) else '#ff932b'
        porcentaje=str(promedio)+'%' if promedio is not None else 'Sin porcentaje'
        col.markdown(f'<div class="trab-area"><div><b>{escape(area)}</b><span>{sum(d["estado"]=="Terminado" for d in grupo)} / {len(grupo)} terminados · {sum(d["estado"]=="Detenido" for d in grupo)} detenidos</span></div><strong>{porcentaje}</strong><div class="trab-track"><i style="width:{promedio or 0}%;background:{color}"></i></div></div>',unsafe_allow_html=True)
    datos=pd.DataFrame(grafico);datos['Avance %']=pd.to_numeric(datos['Avance %'],errors='coerce')
    st.bar_chart(datos,x='Área',y='Avance %',color='#ff932b',height=240)
    st.caption(f"Promedio de los porcentajes registrados, con igual peso por trabajo. {sum(d['avance'] is None for d in filas)} trabajos sin porcentaje. No representa horas ni confirma pruebas.")
    grupos=db.lineas(filas);listas=sum(g['partida']=='Lista según registros' for g in grupos)
    st.subheader('Preparación para la partida')
    st.write(f"**{listas} de {len(grupos)} grupos de área / línea listos según los registros.**")
    cols=st.columns(2)
    for i,g in enumerate(grupos):
        listo=g['partida']=='Lista según registros'
        cols[i%2].markdown(f'<div class="trab-readiness"><b>{escape(g["línea"])}</b><span class="trab-pill {"ready" if listo else "pending"}">{"Listo según registros" if listo else "Pendiente"}</span></div>',unsafe_allow_html=True)
    st.caption('Se exige trabajo terminado, prueba aprobada o no requerida documentada y ausencia de pendientes. Verificar operativamente antes de partir.')
    alertas=[d for d in filas if d['estado']=='Detenido' or d.get('pendiente')]
    if alertas:
        st.subheader('Requiere atención')
        for d in alertas[:5]:st.warning(f"{d['area']} · OT {d.get('ot') or '#'+str(d['id'])}: {d.get('pendiente') or 'Trabajo detenido'}")
        if len(alertas)>5:st.caption(f"Hay {len(alertas)} trabajos con pendientes o bloqueos; consulta el informe para el detalle completo.")
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


def _chat(u,n):
    if not db.puede_chat(u):
        st.error('Solo supervisores, coordinadores de mantenimiento o administración pueden registrar mensajes.');return
    filas=db.trabajos(u['correo'],n)
    opciones=[d for d in filas if db.puede_actualizar(u,d)]
    if not opciones:
        st.info('No hay trabajos disponibles para actualizar en esta programación.');return
    pendiente_key=f'trab_chat_pendiente_{n}'
    destino_key=f'trab_chat_destino_{n}'
    seleccionado_key=f'trab_chat_activo_{n}'
    mensaje=None;fotos=[]
    with st.chat_message('assistant'):
        st.write('Cuéntame cómo va la pega. Después elegimos a qué trabajo corresponde, y yo te ayudo a ordenar el avance.')
    pendiente=st.session_state.get(pendiente_key)
    if pendiente:
        with st.chat_message('user'):st.write(pendiente['mensaje'])
        with st.chat_message('assistant'):
            st.write('¿A qué trabajo corresponde esta novedad?')
            buscar=st.text_input('Buscar por OT, área o descripción',key=f'trab_chat_buscar_{n}')
            tokens=set(re.findall(r'\w{3,}',pendiente['mensaje'].lower()))
            def puntaje(d):
                return (100 if d.get('ot') and d['ot'] in pendiente['mensaje'] else 0)+len(tokens & set(re.findall(r'\w{3,}',(d['descripcion']+' '+d['area']).lower())))
            candidatas=sorted(opciones,key=puntaje,reverse=True)
            if buscar:candidatas=[d for d in candidatas if buscar.lower() in (str(d.get('ot',''))+' '+d['descripcion']+' '+d['area']).lower()]
            elegido=st.selectbox('Trabajo para esta novedad',[None]+[d['id'] for d in candidatas],key=f'trab_chat_elegir_{n}',format_func=lambda i:'Selecciona el trabajo' if i is None else next(f"{d['area']} · OT {d.get('ot') or '#'+str(i)} · {d['descripcion']}" for d in candidatas if d['id']==i))
            if st.button('Registrar en este trabajo',disabled=elegido is None,type='primary'):
                st.session_state[destino_key]=elegido;st.rerun()
            if st.button('Descartar novedad sin guardar'):
                st.session_state.pop(pendiente_key,None);st.session_state.pop(destino_key,None);st.rerun()
        if not st.session_state.get(destino_key):return
        ident=st.session_state.pop(destino_key)
        if ident not in {d['id'] for d in opciones}:st.error('El trabajo ya no está disponible.');return
        st.session_state[seleccionado_key]=ident
        mensaje=pendiente['mensaje'];fotos=pendiente['fotos']
    else:
        ident=st.session_state.get(seleccionado_key)
        if ident not in {d['id'] for d in opciones}:ident=None
    if ident:
        d=next(x for x in opciones if x['id']==ident)
        with st.chat_message('assistant'):st.write(f"**{d['area']} · {d['descripcion']}** · {d['estado']} · Prueba: {d['prueba']}")
        for h in d['historial'][-12:]:
            with st.chat_message('user'):
                st.caption(f"{h['nombre']} · {_fecha(h['fecha'])}")
                st.write(h.get('mensaje') or f"{h['estado']} · Prueba: {h['prueba']}")
    with st.expander('Adjuntar fotos (opcional)'):
        adjuntos=st.file_uploader('Máximo 3 JPG/PNG de hasta 2 MB',type=['jpg','jpeg','png'],accept_multiple_files=True,key=f'trab_chat_adjuntos_{n}')
    escrito=st.chat_input('Escribe el avance, hallazgo o pendiente…',key=f'trab_chat_entrada_{n}',disabled=bool(pendiente))
    if escrito:
        if len(escrito)>10000 or len(adjuntos or [])>3 or any(f.size>2*1024*1024 for f in adjuntos or []):
            st.error('Máximo 10.000 caracteres y 3 fotos de hasta 2 MB.');return
        st.session_state[pendiente_key]=dict(mensaje=escrito,fotos=[(f.name,f.getvalue()) for f in adjuntos or []])
        st.session_state.pop(f'trab_chat_elegir_{n}',None);st.session_state.pop(f'trab_chat_buscar_{n}',None);st.rerun()
    if not ident:return
    clave=f'trab_chat_propuesta_{n}_{ident}'
    if mensaje:
        cambio={k:d[k] for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba')}
        try:
            version=db.actualizar(u['correo'],n,ident,d['version'],cambio,fotos,mensaje=mensaje)
            st.session_state.pop(clave,None)
            st.session_state.pop(pendiente_key,None)
            try:
                from ia.avance_trabajos import preparar_propuesta
                with st.spinner('GearBot está ordenando la novedad…'):propuesta=preparar_propuesta(d,mensaje)
                if propuesta:
                    nuevo=dict(cambio);nuevo.update(propuesta)
                    if nuevo['estado']=='Terminado' and 'avance' not in propuesta:nuevo['avance']=100; nuevo.setdefault('origen_avance','estado_supervisor')
                    elif nuevo['estado']=='Pendiente' and 'avance' not in propuesta:nuevo['avance']=0
                    elif 'estado' in propuesta and 'avance' not in propuesta and d['estado']=='Pendiente':nuevo['avance']=None
                    if 'hallazgos' in propuesta and d['hallazgos'] and propuesta['hallazgos']:
                        nuevo['hallazgos']=d['hallazgos']+'\n'+propuesta['hallazgos']
                    st.session_state[clave]=dict(version=version,cambio=nuevo)
            except Exception:
                st.session_state['trab_flash']='Novedad guardada. GearBot no pudo ordenarla ahora; puedes usar los estados rápidos.'
            st.session_state.pop(f'trab_revision_{n}_{ident}',None)
            st.session_state['trab_limpiar_form']=[f'trab_chat_adjuntos_{n}',f'trab_form_{ident}_']
            st.rerun()
        except ValueError as exc:st.error(str(exc))
    propuesta=st.session_state.get(clave)
    if propuesta:
        obsoleta=d['version']!=propuesta['version']
        with st.chat_message('assistant'):
            st.write('Propuesta de GearBot para confirmar:')
            if propuesta['cambio'].get('etapas'):
                st.dataframe([{'Etapa':e['etapa'],'Peso %':e['peso'],'Reconocida como terminada':i+1 in propuesta['cambio'].get('etapas_confirmadas',[])} for i,e in enumerate(propuesta['cambio']['etapas'])],hide_index=True)
            st.dataframe([{'Dato':k.replace('_',' ').capitalize(),'Valor':({'estimado_etapas':'Estimado por etapas','informado_supervisor':'Informado por supervisor','estado_supervisor':'Estado confirmado por supervisor'}.get(v,v) if k=='origen_avance' else str(v)) if v is not None else 'Sin porcentaje informado'} for k,v in propuesta['cambio'].items() if k not in ('etapas','etapas_confirmadas','plan_nuevo')],hide_index=True)
            if obsoleta:st.warning('El trabajo recibió otra actualización. Descarta esta propuesta y revisa el registro actual.')
            a,b=st.columns(2)
            if a.button('Confirmar actualización',key=f'trab_chat_confirmar_{ident}',disabled=obsoleta,type='primary'):
                try:
                    db.actualizar(u['correo'],n,ident,propuesta['version'],propuesta['cambio'],mensaje='Actualización revisada y confirmada por el responsable de turno.')
                    st.session_state.pop(clave,None);st.session_state.pop(f'trab_revision_{n}_{ident}',None);st.session_state['trab_limpiar_form']=f'trab_form_{ident}_';st.session_state['trab_flash']='Estado actualizado.';st.rerun()
                except ValueError as exc:st.error(str(exc))
            if b.button('Conservar solo el mensaje',key=f'trab_chat_descartar_{ident}'):
                st.session_state.pop(clave,None);st.rerun()
    st.write('**Estados rápidos**')
    a,b=st.columns(2)
    for col,accion in [(a,'Iniciado'),(b,'Trabajo terminado')]:
        if col.button(accion,key=f'trab_chat_rapido_{ident}_{accion}'):
            cambio={k:d[k] for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba')}
            cambio['estado']='En ejecución' if accion=='Iniciado' else 'Terminado'
            cambio['avance']=None if accion=='Iniciado' else 100
            cambio['origen_avance']='estado_supervisor'
            try:
                db.actualizar(u['correo'],n,ident,d['version'],cambio,mensaje=accion+' registrado por el responsable de turno.')
                st.session_state.pop(clave,None);st.session_state.pop(f'trab_revision_{n}_{ident}',None);st.session_state['trab_limpiar_form']=f'trab_form_{ident}_';st.rerun()
            except ValueError as exc:st.error(str(exc))
    if db.gestor(u):_plan_etapas(u,n,d)
    with st.expander('Registrar bloqueo, resultado de prueba o corregir datos'):
        _actualizar(u,n,ident)


def _reportes(u,p):
    from ia.resumen_turno import resumen_base, mejorar_resumen
    n=p['id'];ahora=datetime.now(ZoneInfo('America/Santiago'));fecha=ahora.date().isoformat()
    turno='Día' if 7<=ahora.hour<19 else 'Noche'
    filas=db.trabajos(u['correo'],n)
    st.subheader('Informe listo para compartir')
    st.caption('Resumen de lo registrado en el programa hasta ahora. Puedes ajustar el texto antes de descargar; los estados y porcentajes del trabajo se conservan.')
    base=resumen_base(filas);pref=f'trab_resumen_{n}_'
    firma=hashlib.sha256(str(base).encode()).hexdigest()
    previo=st.session_state.get(pref+'base')
    if previo is None or all(st.session_state.get(pref+k)==previo[k] for k in ('comentario','sugerencias')):
        for k in ('comentario','sugerencias'):st.session_state[pref+k]=base[k]
        st.session_state[pref+'fuente']=firma;st.session_state[pref+'base']=base
    if st.session_state.get(pref+'fuente')!=firma:
        st.info('Hay nuevas novedades en la bitácora. Actualiza el resumen desde el chat o revísalo con GearBot antes de descargar.')
    a,b=st.columns(2)
    if a.button('Actualizar resumen desde el chat'):
        st.session_state[pref+'comentario']=base['comentario'];st.session_state[pref+'sugerencias']=base['sugerencias'];st.session_state[pref+'fuente']=firma;st.session_state[pref+'base']=base
    if b.button('Mejorar redacción con GearBot'):
        try:
            with st.spinner('GearBot prepara el resumen…'):
                nuevo=mejorar_resumen(filas,{k:st.session_state[pref+k] for k in ('comentario','sugerencias')})
            st.session_state[pref+'comentario']=nuevo['comentario'];st.session_state[pref+'sugerencias']=nuevo['sugerencias'];st.session_state[pref+'fuente']=firma;st.session_state[pref+'base']=base
            st.success('Redacción ajustada. Revisa el resumen antes de descargar.')
        except Exception:st.warning('GearBot no está disponible ahora. Tu resumen se conserva y puedes descargarlo.')
    comentario=st.text_area('Resumen de ejecución',key=pref+'comentario',height=240)
    sugerencias=st.text_area('Pendientes y sugerencias',key=pref+'sugerencias',height=120)
    actual=dict(titulo=p['titulo'],centro=p['centro'],fecha=fecha,turno=turno,comentario=comentario,sugerencias=sugerencias,autor=u['correo'],nombre=u['nombre'],generado=datetime.utcnow().isoformat(),trabajos=filas,lineas=db.lineas(filas))
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


def mostrar_trabajos():
    limpiar=st.session_state.pop('trab_limpiar_form',None)
    if limpiar:
        for k in list(st.session_state):
            if str(k).startswith(tuple(limpiar) if isinstance(limpiar,list) else limpiar):st.session_state.pop(k,None)
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
