"""Módulo independiente: historial, oportunidades ADF y efectividad."""
from __future__ import annotations
import datetime as dt
import json
import re
import streamlit as st
import html
import math
import unicodedata
from difflib import SequenceMatcher
from database.vinculos_efectividad import obtener_vinculos, confirmar_vinculo, reabrir_adf_por_reincidencia, obtener_fechas_manuales, guardar_fechas_manuales
from collections import defaultdict

from sqlalchemy.orm import Session
from database.conexion import engine
from database.historial_fallas import (crear_tablas_historial,procesar_excel,datos,grupos,prioridad,plazo_sugerido,adfs_vinculados,estado_efectividad,ExcepcionADF,SeguimientoADF)

def _admin(usuario):return bool(usuario.get('es_admin'))
def _autorizado(usuario):return bool(usuario.get('es_admin') or usuario.get('rol') in ('ingeniero','jefe','subgerente','supervisor','ingeniero_confiabilidad'))

def _filtros(avisos,prefijo):
    areas=sorted({a.area for a in avisos})
    a=st.selectbox('Área',['Todas']+areas,key=f'{prefijo}_area')
    candidatos=[x for x in avisos if a=='Todas' or x.area==a]
    equipos={x.equipo_codigo:x.equipo_nombre for x in candidatos}
    codigos=sorted(equipos,key=lambda x:equipos[x])
    e=st.selectbox('Equipo',['Todos']+codigos,format_func=lambda x:'Todos los equipos' if x=='Todos' else f'{equipos[x]} · {x}',key=f'{prefijo}_equipo')
    p=st.selectbox('Período',['Histórico','30 días','90 días','12 meses'],key=f'{prefijo}_periodo')
    corte=max((x.fecha for x in avisos),default=dt.date.today())
    dias={'30 días':30,'90 días':90,'12 meses':365}.get(p)
    return [x for x in candidatos if (e=='Todos' or x.equipo_codigo==e) and (dias is None or (corte-x.fecha).days<=dias)]

def _avisos_adf(adf):
    return set(re.findall(r'\d{7,}', str(getattr(adf, 'aviso_sap', '') or '')))


def _normalizar(v):
    return str(v or '').strip().lower()


def _planes(adf):
    try:
        planes = json.loads(getattr(adf, 'plan_prevencion', '') or '[]')
    except (ValueError, TypeError):
        return []
    return [p for p in planes if isinstance(p, dict)] if isinstance(planes, list) else []


def _clasificar_planes(planes):
    """Los planes archivados/cancelados no son ejecutados ni pendientes activos."""
    activos, cancelados, archivados = [], [], []
    for p in planes:
        if (p.get("eliminado_administrador") or
                str(p.get("estado_administrativo") or "").strip().lower() in {"eliminado", "archivado", "eliminado (archivado)"}):
            archivados.append(p)
        elif p.get("estado_administrativo") == "Cancelado":
            cancelados.append(p)
        else:
            activos.append(p)
    return activos, cancelados, archivados


def _fecha_ejecucion(planes):
    """Última fecha acreditada de ejecución, solo de planes activos."""
    fechas = []
    for p in planes:
        fecha = p.get("fecha_ejecucion")
        if not fecha:
            return None
        try:
            fechas.append(dt.date.fromisoformat(str(fecha)[:10]))
        except (ValueError, TypeError):
            return None
    return max(fechas) if fechas else None


def _resumen(e):
    base=' '.join(str(e.descripcion or '').split())
    detalle=' '.join(str(e.texto or '').split())
    if detalle and detalle.lower() not in base.lower():
        base = f'{base}. {detalle}'.strip('. ')
    return base[:280] + ('…' if len(base)>280 else '')


def _filtros_visuales(avisos):
    areas=sorted({e.area for e in avisos if e.area})
    c1,c2,c3=st.columns([1,2,1])
    with c1:
        area=st.selectbox('Área',['Todas']+areas,key='hf_area_v3')
    subset=[e for e in avisos if area=='Todas' or e.area==area]
    equipos={e.equipo_codigo:e.equipo_nombre for e in subset if e.equipo_codigo}
    with c2:
        equipo=st.selectbox('Equipo',['Todos']+sorted(equipos),format_func=lambda x:'Todos los equipos' if x=='Todos' else f'{equipos[x]} · {x}',key='hf_equipo_v3')
    with c3:
        periodo=st.selectbox('Período',['Año actual','2026','2025','Últimos 90 días','Todo el historial'],key='hf_periodo_v3')
    corte=max((e.fecha for e in avisos),default=dt.date.today())
    return [e for e in subset if (equipo=='Todos' or e.equipo_codigo==equipo)
        and (periodo=='Todo el historial' or (periodo=='Año actual' and e.fecha.year==dt.date.today().year)
             or (periodo in ('2026','2025') and e.fecha.year==int(periodo))
             or (periodo=='Últimos 90 días' and 0 <= (corte-e.fecha).days <= 90))]


def _patrones(avisos):
    grupos_validos=defaultdict(list)
    for e in avisos:
        if e.equipo_codigo and e.modo and e.modo!='Sin clasificar':
            grupos_validos[(e.equipo_codigo,e.modo)].append(e)
    return [(prioridad(v),sorted(v,key=lambda e:e.fecha)) for v in grupos_validos.values() if len(v)>=2]


def _texto_adf(eventos):
    primero,ultimo=eventos[0],eventos[-1]
    total=sum(max(0,float(e.tp_min or 0)) for e in eventos)
    duracion=(ultimo.fecha-primero.fecha).days
    descripciones=[]
    for e in eventos:
        d=' '.join(str(e.descripcion or '').split())
        if d and d.lower() not in [x.lower() for x in descripciones]:descripciones.append(d)
    sintomas='; '.join(descripciones[:3]) if descripciones else 'descripciones no disponibles'
    return (f'En el equipo {ultimo.equipo_nombre} ({ultimo.equipo_codigo}), área {ultimo.area}, '
        f'se registraron {len(eventos)} avisos asociados preliminarmente al modo de falla «{ultimo.modo}» '
        f'entre el {primero.fecha:%d/%m/%Y} y el {ultimo.fecha:%d/%m/%Y} '
        f'({duracion} días), acumulando {total:.0f} minutos de tiempo perdido. '
        f'Los síntomas descritos incluyen: {sintomas}. '
        'Se recomienda realizar un ADF para verificar si los eventos comparten el mismo fenómeno y causa raíz, '
        'identificar condiciones de recurrencia y definir acciones preventivas verificables. '
        'La similitud es preliminar y no constituye una causa raíz confirmada.')


def _timeline(eventos, minimo=3):
    """Cronología de patrones, nunca un volcado de avisos individuales."""
    patrones = sorted(
        [(ev[0].fecha, ev) for _, ev in _patrones(eventos) if len(ev) >= minimo],
        key=lambda x: x[0],
    )
    st.markdown("""<style>
    .hf-v10-line{border-left:3px solid #4f93bf;margin:18px 0 0 18px;padding:0 0 1px 25px}
    .hf-v10-card{border:1px solid rgba(140,160,175,.27);border-left:5px solid var(--hito);
       background:rgba(110,145,170,.10);border-radius:13px;padding:16px 19px;
       margin:0 0 12px;position:relative}
    .hf-v10-card:before{content:'';position:absolute;left:-38px;top:17px;
       width:16px;height:16px;border-radius:50%;background:var(--hito);
       border:3px solid #20252c}
    .hf-v10-date{font-weight:700;font-size:.86rem;color:#91c9e9}
    .hf-v10-name{font-size:1.08rem;font-weight:750;margin:7px 0}
    .hf-v10-text{line-height:1.55}
    .hf-v10-pill{display:inline-block;border:1px solid var(--hito);
       padding:3px 9px;border-radius:99px;font-size:.8rem;margin:8px 7px 0 0}
    </style>""",unsafe_allow_html=True)
    if not patrones:
        st.info(f'No hay patrones con {minimo} o más avisos similares para estos filtros.')
        return
    total_avisos = sum(len(ev) for _,ev in patrones)
    tp_total = sum(max(0,float(e.tp_min or 0)) for _,ev in patrones for e in ev)
    c1,c2,c3=st.columns(3)
    c1.metric('Patrones relevantes',len(patrones))
    c2.metric('Avisos agrupados',total_avisos)
    c3.metric('TP acumulado',f'{tp_total:,.1f} min')
    st.caption('Agrupación preliminar por equipo y modo de falla. '
               'No implica causa raíz común confirmada.')
    for i,(_, ev) in enumerate(patrones):
        primero,ultimo=ev[0],ev[-1]
        tp=sum(max(0,float(e.tp_min or 0)) for e in ev)
        lapso=(ultimo.fecha-primero.fecha).days
        # La clasificación indica la prioridad del patrón, no la gravedad de un aviso individual.
        color='#D85D55' if len(ev)>=5 else '#E7A33B' if len(ev)>=4 else '#579DD4'
        etiqueta='Reincidencia prioritaria' if len(ev)>=5 else 'Patrón recurrente' if len(ev)>=4 else 'Posible reincidencia'
        descripciones=[]
        for e in ev:
            texto=' '.join(str(e.descripcion or '').split()).strip(' .')
            if texto and texto.casefold() not in {d.casefold() for d in descripciones}:
                descripciones.append(texto)
        sintomas='; '.join(descripciones[:2]) if descripciones else 'sin descripción de síntoma'
        if len(sintomas)>180:sintomas=sintomas[:177].rsplit(' ',1)[0]+'…'
        narrativa=(f'Se registraron {len(ev)} avisos clasificados preliminarmente como '
                   f'«{ultimo.modo}» en {lapso} días, con {tp:.1f} minutos de TP acumulado. '
                   f'Entre los síntomas documentados: {sintomas}.')
        st.markdown(
            f'<div class="hf-v10-line"><div class="hf-v10-card" style="--hito:{color}">'
            f'<div class="hf-v10-date">{primero.fecha:%d/%m/%Y} — {ultimo.fecha:%d/%m/%Y}</div>'
            f'<div class="hf-v10-name">{html.escape(str(ultimo.equipo_nombre or ultimo.equipo_codigo))}'
            f' · {html.escape(str(ultimo.modo))}</div>'
            f'<div class="hf-v10-text">{html.escape(narrativa)}</div>'
            f'<span class="hf-v10-pill">{len(ev)} fallas relacionadas</span>'
            f'<span class="hf-v10-pill">{tp:.1f} min TP</span>'
            f'<span class="hf-v10-pill">{etiqueta}</span>'
            '</div></div>',unsafe_allow_html=True)
        with st.expander(f'Antecedentes de este hito · {len(ev)} avisos',expanded=False):
            st.caption('Avisos de origen. El texto completo de SAP solo se abre si lo necesitas.')
            for e in ev:
                st.markdown(f'**{e.fecha:%d/%m/%Y} · Aviso {e.aviso} · {float(e.tp_min or 0):g} min TP**')
                st.write(' '.join(str(e.descripcion or 'Sin descripción breve').split()))
                with st.expander(f'Ver texto SAP · {e.aviso}',expanded=False):
                    st.write(e.texto or 'No hay texto adicional en SAP.')
        st.divider()
    st.info('Análisis preliminar: los grupos comparten equipo y categoría de falla. '
            'Antes de generar un ADF, revisar los avisos y confirmar que los síntomas '
            'y condiciones de operación sean realmente comparables.')

def _tokens(texto):
    limpio = ''.join(c for c in unicodedata.normalize('NFKD', str(texto or '').lower())
                     if not unicodedata.combining(c))
    stop = {'de','del','la','el','en','por','con','para','se','no','un','una','equipo','falla','maquina','aviso'}
    return {x for x in re.findall(r'[a-z0-9]{3,}', limpio) if x not in stop}


def _similitud(a, b):
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def _fecha_adf(adf):
    for campo in ('fecha_creacion','fecha_envio_validacion','fecha_aprobacion_supervisor'):
        valor = getattr(adf, campo, None)
        if valor:
            return valor.date() if isinstance(valor, dt.datetime) else valor
    return None


def _origen_candidatos(adf, avisos, fecha_manual=None):
    fecha = fecha_manual or _fecha_adf(adf)
    equipo = _normalizar(getattr(adf,'numero_equipo',''))
    tp_adf = float(getattr(adf,'tiempo_perdido_h',0) or 0) * 60
    relato = ' '.join(str(getattr(adf,k,'') or '') for k in ('relato_original','efecto','equipo'))
    candidatos = []
    for e in avisos:
        if equipo and _normalizar(e.equipo_codigo) != equipo:
            continue
        if not equipo and _normalizar(getattr(adf,'equipo','')) != _normalizar(e.equipo_nombre):
            continue
        delta = abs((fecha-e.fecha).days) if fecha else 9999
        if fecha and (e.fecha > fecha + dt.timedelta(days=2) or delta > 120):
            continue
        sim = _similitud(relato, _resumen(e))
        tp = float(e.tp_min or 0)
        tp_sim = 1.0 - min(1.0,abs(tp-tp_adf)/max(tp,tp_adf,1)) if tp_adf else 0.0
        fecha_sim = max(0,1-delta/120) if fecha else 0
        score = .52*sim + .28*tp_sim + .20*fecha_sim
        candidatos.append((score,e))
    return sorted(candidatos,key=lambda x:x[0],reverse=True)[:4]


def _reincidencias(origen, avisos, inicio, plazo, vinculados):
    fin = inicio + dt.timedelta(days=plazo)
    resultado=[]
    base=_resumen(origen)
    for e in avisos:
        if e.aviso == origen.aviso or e.equipo_codigo != origen.equipo_codigo:
            continue
        if not inicio < e.fecha <= fin:
            continue
        sim=_similitud(base,_resumen(e))
        mismo_modo = bool(e.modo and e.modo != 'Sin clasificar' and e.modo == origen.modo)
        if e.aviso in vinculados or (sim >= .33 and mismo_modo) or sim >= .58:
            resultado.append((e,sim,e.aviso in vinculados))
    return sorted(resultado,key=lambda x:x[0].fecha)


def _seguimiento(adfs,avisos,filtrados,ultima):
    st.markdown('### Seguimiento de efectividad de ADF')
    st.caption('Cruce SAP por equipo, fecha, TP y descripción. Las coincidencias sugeridas requieren confirmación; no se atribuyen causas automáticamente.')
    usuario=st.session_state.get('usuario_actual') or {}
    autorizado=_autorizado(usuario)
    por_aviso={str(e.aviso):e for e in avisos}
    try:
        vinculos=obtener_vinculos()
    except Exception as exc:
        st.error(f'No fue posible leer los vínculos de efectividad: {exc}')
        return
    try:
        fechas_manuales=obtener_fechas_manuales()
    except Exception as exc:
        st.error(f'No se pudieron leer las fechas manuales: {exc}')
        return
    por_adf={}
    for aid,aviso,tipo,autor,nota in vinculos:
        por_adf.setdefault(aid,{}).setdefault(tipo,[]).append(aviso)
    registros=[]
    sin_planes=sin_activos=pendientes=0
    for adf in adfs:
        planes=_planes(adf)
        if not planes:
            sin_planes+=1;continue
        activos,cancelados,archivados=_clasificar_planes(planes)
        if not activos:
            sin_activos+=1;continue
        if any(p.get('estado_ejecucion') != 'Ejecutado verificado' for p in activos):
            pendientes+=1;continue
        inicio_automatico=_fecha_ejecucion(activos)
        fecha_evento_manual, inicio_manual = fechas_manuales.get(adf.id, (None,None))
        # La fecha manual es la fecha REAL confirmada, por encima de una
        # fecha estimada o del día de validación que el flujo haya guardado.
        inicio=inicio_manual or inicio_automatico
        ids=por_adf.get(adf.id,{})
        origen=next((por_aviso[x] for x in ids.get('origen',[]) if x in por_aviso),None)
        ids_adf=_avisos_adf(adf)
        directo=[e for e in avisos if str(e.aviso) in ids_adf]
        if origen is None and len(directo)==1:
            origen=directo[0]
        # Si el ADF ya registra aviso SAP, es la fuente principal, no inferir otro.
        candidatos=_origen_candidatos(adf,avisos,fecha_evento_manual) if origen is None and not ids_adf else []
        if origen and inicio:
            asociados=[e for e in avisos if e.equipo_codigo==origen.equipo_codigo and e.modo==origen.modo and e.fecha<=inicio]
            plazo,confianza,razon=plazo_sugerido(asociados)
            plazo=max(1,int(plazo))
            # Solo se evalúan días respaldados por el historial SAP importado.
            # No avanzar a la fecha actual si no hay importación nueva.
            corte=ultima if ultima else inicio
            transcurridos=max(0,(corte-inicio).days)
            hallados=_reincidencias(origen,[e for e in avisos if ultima and e.fecha <= ultima],inicio,plazo,set(ids.get('reincidencia',[])))
            confirmados=[x for x in hallados if x[2]]
            sospechas=[x for x in hallados if not x[2]]
            estado='Reincidencia' if confirmados else ('Por verificar' if sospechas else ('Efectivo' if transcurridos>=plazo and ultima and ultima>=inicio+dt.timedelta(days=plazo) else 'En evaluación'))
        else:
            plazo=transcurridos=0;confianza='';razon='';hallados=[];sospechas=[];confirmados=[]
            estado='Sin fecha' if origen else 'Vincular origen'
        registros.append((adf,activos,cancelados,archivados,inicio,origen,candidatos,plazo,transcurridos,estado,razon,sospechas,confirmados,ids,fecha_evento_manual))
    counts={k:sum(1 for r in registros if r[9]==k) for k in ('En evaluación','Efectivo','Reincidencia')}
    c1,c2,c3=st.columns(3)
    c1.metric('En evaluación',counts['En evaluación'])
    c2.metric('Período cumplido',counts['Efectivo'])
    c3.metric('Reincidencias confirmadas',counts['Reincidencia'])
    st.caption('Período cumplido = sin reincidencias detectadas en los avisos SAP importados hasta el fin del plazo. No garantiza ausencia de fallas no registradas.')
    if ultima:st.caption(f'Última fecha de datos SAP: {ultima:%d/%m/%Y}')
    filtro=st.selectbox('Mostrar',['Todos','En evaluación','Efectivo','Reincidencia','Por verificar','Vincular origen','Sin fecha'],key='hf_ef_filtro_v15')
    for adf,activos,cancelados,archivados,inicio,origen,candidatos,plazo,dias,estado,razon,sospechas,confirmados,ids,fecha_evento_manual in registros:
        if filtro!='Todos' and filtro!=estado:continue
        with st.container(border=True):
            cab,est=st.columns([4,1])
            cab.markdown(f'**ADF #{adf.id} · {adf.equipo}**')
            est.markdown({'Efectivo':'🟢','Reincidencia':'🔴','En evaluación':'🟡','Por verificar':'🟠'}.get(estado,'⚪')+' **'+estado+'**')
            if origen:
                st.caption(f'Aviso de origen: {origen.aviso} · {origen.fecha:%d/%m/%Y} · TP {origen.tp_min:g} min')
            elif _avisos_adf(adf):
                st.caption('Aviso registrado en ADF: ' + ', '.join(sorted(_avisos_adf(adf))))
                st.warning('El aviso indicado en el ADF no está en los datos SAP importados. No se sustituye por otro aviso automáticamente.')
            if fecha_evento_manual and not origen:
                st.caption(f'Fecha del evento registrada manualmente: {fecha_evento_manual:%d/%m/%Y}')
            if inicio and origen:
                color='🔴' if estado=='Reincidencia' else '🟢' if estado=='Efectivo' else '🟡'
                st.markdown(f'{color} **{min(dias,plazo)} / {plazo} días evaluados** · {max(0,plazo-dias)} restantes')
                st.caption(f'Inicio de efectividad: {inicio:%d/%m/%Y}' +
                           (' · Fecha confirmada manualmente' if fechas_manuales.get(adf.id,(None,None))[1] else
                            ' · Fecha registrada en el plan (verificar si es real)'))
                st.progress(min(1.0,dias/plazo))
                if ultima:
                    st.caption(f'Fecha de corte SAP: {ultima:%d/%m/%Y}. El contador no avanza más allá de esa fecha.')
                    if inicio > ultima:
                        st.info('La ejecución del último plan es posterior a la fecha de corte SAP. '
                                'Por eso aparecen 0 días evaluados; importa avisos SAP más recientes '
                                'o corrige la fecha de ejecución si está equivocada.')
                if estado=='Efectivo':st.success('Plazo cumplido sin reincidencias similares detectadas en el historial cargado.')
            elif not inicio:
                st.warning('Falta fecha de ejecución verificable en los planes activos; no se inicia el conteo.')
            # No mostrar archivados/eliminados en ningún contador ni detalle de efectividad.
            # La auditoría de eliminación permanece únicamente en administración.
            st.caption(f'{len(activos)} plan(es) activo(s) ejecutado(s) y verificado(s)')
            if cancelados:
                st.caption(f'{len(cancelados)} plan(es) cancelado(s) con justificación')
            if autorizado:
                with st.expander('Verificar o corregir fechas del ADF', expanded=False):
                    st.caption('La falla original sirve para identificar el aviso SAP. '
                               'El período de efectividad empieza al implementar realmente '
                               'el último plan activo, no al crear el ADF ni al subir su respaldo.')
                    sugerida=fecha_evento_manual or (origen.fecha if origen else None) or _fecha_adf(adf) or dt.date.today()
                    fecha_evento=st.date_input('Fecha real de la falla original',value=sugerida,key=f'ef_fecha_evento_{adf.id}')
                    inicio_sugerido=inicio or fecha_evento
                    fecha_inicio=st.date_input('Fecha real de implementación del último plan activo',
                                               value=inicio_sugerido,key=f'ef_inicio_{adf.id}')
                    if ultima:
                        st.caption(f'Último dato SAP disponible: {ultima:%d/%m/%Y}. '
                                   'Si el plan se implementó después, habrá 0 días evaluados hasta importar datos posteriores.')
                    if st.button('Guardar fechas verificadas',key=f'ef_guardar_fechas_{adf.id}'):
                        try:
                            guardar_fechas_manuales(adf.id,usuario,fecha_evento,fecha_inicio)
                            st.success('Fechas registradas con trazabilidad.');st.rerun()
                        except Exception as exc:st.error(str(exc))
            if not origen:
                if candidatos:
                    st.info('Aviso SAP de origen sugerido automáticamente. Confirma antes de asociarlo.')
                    for score,e in candidatos[:3]:
                        st.caption(f'{e.aviso} · {e.fecha:%d/%m/%Y} · TP {e.tp_min:g} min · coincidencia {score:.0%} · {_resumen(e)[:140]}')
                    if autorizado:
                        opcion=st.selectbox('Aviso de origen a confirmar',['Seleccionar']+[str(e.aviso) for _,e in candidatos],key=f'ef_origen_{adf.id}')
                        if st.button('Confirmar aviso de origen',key=f'ef_confirmar_origen_{adf.id}',disabled=opcion=='Seleccionar'):
                            try:
                                confirmar_vinculo(adf.id,opcion,'origen',usuario,'Cruce SAP validado por usuario')
                                st.rerun()
                            except Exception as exc:st.error(str(exc))
                elif not _avisos_adf(adf):
                    st.info('Este ADF no tiene aviso SAP. Registra la fecha manual y vincula el aviso cuando exista.')
            if sospechas:
                st.warning(f'{len(sospechas)} posible(s) reincidencia(s). Requieren confirmación antes de marcar el ADF en rojo.')
                for e,sim,_ in sospechas:
                    with st.expander(f'Aviso {e.aviso} · {e.fecha:%d/%m/%Y} · similitud {sim:.0%}'):
                        st.write(_resumen(e))
                        if autorizado and st.button('Confirmar reincidencia y vincular',key=f'ef_vincular_{adf.id}_{e.aviso}'):
                            try:
                                confirmar_vinculo(adf.id,e.aviso,'reincidencia',usuario,'Reincidencia confirmada tras revisión')
                                st.rerun()
                            except Exception as exc:st.error(str(exc))
            if confirmados:
                st.error('Reincidencia confirmada dentro del plazo. Se conservan los avisos vinculados.')
                for e,sim,_ in confirmados:st.caption(f'🔗 Aviso {e.aviso} · {e.fecha:%d/%m/%Y} · {_resumen(e)[:140]}')
                st.info('Puedes reabrir el ADF para corregir su análisis. Se conservan planes, evidencias y avisos vinculados; se registra auditoría.')
                if autorizado:
                    confirmacion=st.checkbox('Confirmo que deseo reabrir este ADF y devolverlo a corrección',key=f'ef_check_reabrir_{adf.id}')
                    if st.button('Reabrir ADF',key=f'ef_reabrir_{adf.id}',disabled=not confirmacion):
                        try:
                            reabrir_adf_por_reincidencia(adf.id,usuario)
                            st.session_state['historial_reapertura_propuesta']={'adf_id':adf.id,'avisos':ids.get('reincidencia',[])}
                            st.success('ADF reabierto y registrado en historial de validación.')
                            st.rerun()
                        except Exception as exc:st.error(str(exc))
            # Detalles exclusivamente técnicos; no mostrar planes eliminados.
            if razon or cancelados:
                with st.expander('Detalles del seguimiento'):
                    if razon:
                        st.write('**Fundamento del plazo:**',razon)
                    for plan in cancelados:
                        st.write('**Plan cancelado:**',plan.get('accion') or plan.get('titulo') or 'Sin título')
                        for audit in plan.get('auditoria_administrativa') or []:
                            st.caption(f'{audit.get("motivo","")} · {audit.get("justificacion","")}')
    if not registros:st.info('No hay ADF con planes activos completamente verificados.')
    with st.expander('Diagnóstico de elegibilidad'):
        st.write(f'Sin planes: {sin_planes} · Sin planes activos: {sin_activos} · Pendientes de ejecución/verificación: {pendientes}')


def mostrar_historial_reincidencias():
    usuario=st.session_state.get('usuario_actual') or {}
    if not _autorizado(usuario):
        st.error('No tienes permisos para consultar el historial.');return
    crear_tablas_historial()
    avisos,adfs,excepciones,seguimientos,ultima=datos()
    sin_ceco=sum(1 for e in avisos if not getattr(e,'centro_costo',''))
    if sin_ceco:
        st.warning(f'{sin_ceco} avisos antiguos no tienen CeCo almacenado. Para clasificarlos por área, vuelve a importar el Excel SAP desde Administración. Hasta entonces figurarán como Sin área asignada.')
    if any(e.area == 'Sin área asignada' and getattr(e,'centro_costo','') for e in avisos):
        st.info('Existen centros de costo no incluidos en la tabla de equivalencias; revisa el mapeo de CeCo.')
    st.title('📈 Historial de Fallas y Reincidencias')
    st.caption('Historia de equipos · TOP 5 de patrones repetitivos · Seguimiento ADF')
    st.info(f'Historial SAP actualizado hasta {ultima:%d/%m/%Y}' if ultima else 'Todavía no hay avisos SAP importados.')
    filtrados=_filtros_visuales(avisos)
    t1,t2,t3=st.tabs(['🕒 Línea de tiempo','🎯 Oportunidades ADF','📊 Efectividad ADF'])
    with t1:
        st.markdown('#### Línea de tiempo · Hitos de fallas recurrentes')
        st.caption('Cada hito resume un grupo de fallas similares, no un aviso individual.')
        minimo=st.selectbox('Mínimo de fallas relacionadas por hito',
                            [3,4,5,2],index=0,key='hf_hitos_min_v10')
        if filtrados:_timeline(filtrados,minimo)
        else:st.info('No hay eventos para el período y equipo seleccionados.')
    with t2:
        st.markdown('#### TOP 5 · Patrones que requieren análisis')
        candidatos=[]
        for punt,eventos in _patrones(filtrados):
            if any(e.aviso in _avisos_adf(a) for e in eventos for a in adfs):continue
            candidatos.append((punt,eventos))
        candidatos.sort(key=lambda x:x[0],reverse=True)
        if not candidatos:st.info('No se detectan patrones repetitivos pendientes con estos filtros.')
        for i,(punt,eventos) in enumerate(candidatos[:5],1):
            primero,ultimo=eventos[0],eventos[-1]
            st.markdown(f'### {i}. {ultimo.equipo_nombre} · {ultimo.modo}')
            c1,c2,c3=st.columns(3)
            c1.metric('Fallas similares',len(eventos))
            c2.metric('TP acumulado',f'{sum(e.tp_min for e in eventos):.0f} min')
            c3.metric('Intervalo',f'{(ultimo.fecha-primero.fecha).days} días')
            st.progress(min(1.,punt/100))
            st.markdown('**Recomendación estructurada para ADF**')
            st.write(_texto_adf(eventos))
            with st.expander('Ver avisos que sustentan la recomendación'):
                for e in eventos:st.write(f'{e.fecha:%d/%m/%Y} · {e.aviso} · {e.tp_min:g} min · {_resumen(e)}')
            if st.button('Validar oportunidad y preparar ADF',key=f'hf_oport_v3_{ultimo.equipo_codigo}_{ultimo.modo}'):
                st.session_state['historial_preparar_adf']={'numero_equipo':ultimo.equipo_codigo,'equipo':ultimo.equipo_nombre,'avisos':[e.aviso for e in eventos],'fenomeno':ultimo.modo,'antecedentes':_texto_adf(eventos)}
                st.warning('Antecedentes preparados. El formulario ADF todavía requiere conexión para precargarlos; no se creó un ADF.')
            st.divider()
    with t3:_seguimiento(adfs,avisos,filtrados,ultima)

def mostrar_importacion_historial():
    usuario=st.session_state.get('usuario_actual') or {}
    if not _admin(usuario):st.error('Solo administradores pueden importar avisos SAP.');st.stop()
    crear_tablas_historial()
    st.subheader('📤 Actualizar historial de fallas SAP')
    st.caption('Solo avisos criticidad A. Se conserva la información estructurada, nunca el Excel original.')
    archivo=st.file_uploader('Archivo mensual SAP (.xlsx)',type=['xlsx'],key='carga_historial_fallas')
    if archivo:
        try:
            vista=procesar_excel(archivo,usuario.get('correo',''),False)
            st.write(f"Avisos válidos: {vista['registros']} · Filas rechazadas: {vista['rechazados']}")
            for e in vista['errores'][:10]:st.warning(e)
            if st.button('Confirmar importación',type='primary'):
                archivo.seek(0)
                resultado=procesar_excel(archivo,usuario.get('correo',''),True)
                st.success(f"Nuevos: {resultado['nuevos']} · Actualizados: {resultado['actualizados']} · Rechazados: {resultado['rechazados']}")
        except Exception as e:st.error(f'No se pudo interpretar el Excel: {e}')
