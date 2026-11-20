"""Módulo independiente: historial, oportunidades ADF y efectividad."""
from __future__ import annotations
import datetime as dt
import json
import re
import streamlit as st
import html
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
        if p.get("eliminado_administrador") or p.get("estado_administrativo") == "Eliminado":
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

def _seguimiento(adfs,avisos,filtrados,ultima):
    st.markdown('#### Efectividad de ADF · Planes completamente ejecutados')
    st.caption('La información se lee directamente desde los planes existentes. No es necesario volver a cargar fechas ni evidencias.')
    visibles=0
    excluidos={'sin_planes':0,'sin_activos':0,'pendientes':0,'sin_vinculo':0,'sin_fecha':0}
    for adf in adfs:
        planes=_planes(adf)
        if not planes:
            excluidos['sin_planes']+=1;continue
        activos,cancelados,archivados=_clasificar_planes(planes)
        if not activos:
            excluidos['sin_activos']+=1
            continue
        # Cancelados/archivados quedan fuera del denominador; no son ejecutados.
        pendientes=[p for p in activos if p.get('estado_ejecucion')!='Ejecutado verificado']
        if pendientes:
            excluidos['pendientes']+=1
            continue
        st.markdown(f'**ADF #{adf.id} · {adf.equipo}**')
        st.success(f'Planes activos completos: {len(activos)}/{len(activos)} (100%).')
        if cancelados or archivados:
            st.warning(
                f'⚠️ {len(cancelados)} plan(es) cancelado(s) y '
                f'{len(archivados)} archivado(s). Se excluyen del cumplimiento, '
                'pero pueden limitar la efectividad de las medidas preventivas.'
            )
            with st.expander('Ver planes no ejecutados y sus justificaciones'):
                for p in cancelados+archivados:
                    st.write(f'**{p.get("accion") or p.get("titulo") or "Plan"}** · '
                             f'{p.get("estado_administrativo") or "Archivado"}')
                    for registro in p.get('auditoria_administrativa') or []:
                        st.caption(f'{registro.get("motivo","")} · {registro.get("justificacion","")}')
        observados=[]
        for p in activos:
            rev=p.get('revision_ia') or {}
            if isinstance(rev,dict) and rev.get('aprobado_con_observacion'):
                observados.append((p.get('titulo') or p.get('descripcion') or 'Plan',
                                   rev.get('observacion_aprobacion') or 'Aprobación con observación'))
        origen=[e for e in avisos if e.aviso in _avisos_adf(adf)]
        if not origen:
            excluidos['sin_vinculo']+=1
            st.markdown(f'**ADF #{adf.id} · {adf.equipo} — Planes completos**')
            st.info('Planes ejecutados y verificados. Falta vincular el aviso SAP de origen para calcular efectividad y reincidencias sin confundir modos de falla.')
            for ix, p in enumerate(activos, 1):
                rev=p.get('revision_ia') or {}
                st.caption(f'Plan {ix} · Confianza respaldo: {rev.get("confianza", "sin dato") if isinstance(rev,dict) else "sin dato"}% · {p.get("estado_respaldo") or "Sin clasificación histórica"}')
            st.divider()
            continue
        if not any(e.aviso in {v.aviso for v in filtrados} for e in origen):continue
        inicio=_fecha_ejecucion(activos)
        if not inicio:
            excluidos['sin_fecha']+=1
            st.info('Planes activos completos, pero falta fecha de ejecución verificable. '
                    'No se puede iniciar el cómputo de días de observación.')
            st.divider()
            continue
        modos={e.modo for e in origen if e.modo and e.modo!='Sin clasificar'}
        if not modos:
            excluidos['sin_vinculo']+=1
            st.info('Falta identificar el modo de falla de los avisos vinculados.')
            st.divider()
            continue
        asociados=[e for e in avisos if e.equipo_codigo==origen[0].equipo_codigo and e.modo in modos]
        plazo,confianza,razon=plazo_sugerido([e for e in asociados if e.fecha<=inicio])
        corte=min(ultima,dt.date.today()) if ultima else inicio
        dias=max(0,(corte-inicio).days)
        posteriores=[e for e in asociados if inicio<e.fecha<=corte]
        visibles+=1
        st.markdown(f'**ADF #{adf.id} · {adf.equipo} · {", ".join(sorted(modos))}**')
        st.progress(min(1.,dias/max(plazo,1)))
        st.caption(f'{dias} / {plazo} días observados · {max(0,plazo-dias)} restantes · Confianza {confianza}')
        st.markdown('**Calidad de respaldos de los planes**')
        for ix, plan in enumerate(activos, 1):
            rev = plan.get('revision_ia') or {}
            porcentaje = rev.get('confianza') if isinstance(rev, dict) else None
            estado_respaldo = plan.get('estado_respaldo') or 'Sin clasificación histórica'
            st.caption(f'Plan {ix}: {estado_respaldo} · Confianza IA: {porcentaje if porcentaje is not None else "sin dato"}%')
            conf = plan.get('confirmacion_mantenimiento') or {}
            if isinstance(conf, dict) and conf.get('fecha_programada'):
                if conf.get('ejecutado'):
                    st.success(f'Plan {ix}: ejecución posterior del mantenimiento confirmada (OT: {conf.get("ot_sap") or "sin OT"}).')
                else:
                    st.warning(f'Plan {ix}: mantenimiento programado para {conf["fecha_programada"]}, pendiente de confirmar ejecución. La creación del plan ADF ya fue cumplida.')

        if observados:
            st.warning(f'{len(observados)} plan(es) aprobado(s) con observaciones. '
                       'La ejecución está completa; revisar estas observaciones al evaluar reincidencias.')
            with st.expander('Observaciones de respaldos aprobados'):
                for nombre, nota in observados:st.write(f'**{nombre}:** {nota}')
        if posteriores:
            st.error(f'{len(posteriores)} posible(s) reincidencia(s) detectada(s): revisar que correspondan a la misma causa.')
            with st.expander('Revisar nuevos antecedentes'):
                for e in posteriores:st.write(f'{e.fecha:%d/%m/%Y} · {e.aviso} · {_resumen(e)}')
                if st.button('Preparar reapertura',key=f'hf_reabrir_v3_{adf.id}'):
                    st.session_state['historial_reapertura_propuesta']={'adf_id':adf.id,'avisos':[e.aviso for e in posteriores]}
                    st.warning('Antecedentes preparados. No se modificó el ADF: falta conectar el flujo de reapertura.')
        elif dias<plazo:st.info('En observación, sin reincidencias similares en los avisos cargados.')
        elif confianza in ('baja','muy baja'):st.warning('Período cumplido; evidencia insuficiente para demostrar efectividad.')
        else:st.success('Sin reincidencias similares durante el período observado. Revisar exposición y control antes de cerrar efectividad.')
        with st.expander('Fundamento del plazo'):st.write(razon)
        st.divider()
    if not visibles:st.info('No hay ADF con seguimiento temporal calculable para los filtros seleccionados. '
                             'Los ADF con planes activos completos se muestran arriba, '
                             'aunque todavía falten vínculos o fechas.')
    with st.expander('Diagnóstico de ADF no elegibles'):
        st.write(f'ADF con planes aún sin ejecutar/verificar: {excluidos["pendientes"]}')
        st.write(f'ADF sin planes estructurados: {excluidos["sin_planes"]}')
        st.write(f'ADF con todos sus planes cancelados/archivados (requieren revisión): {excluidos["sin_activos"]}')
        st.write(f'ADF sin aviso SAP coincidente: {excluidos["sin_vinculo"]}')
        st.write(f'ADF sin fecha de ejecución verificada: {excluidos["sin_fecha"]}')
        st.caption('Si el ADF esperado no aparece, revisa el estado real de cada plan y su número de aviso SAP. No se alteraron estados ni validaciones.')


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
