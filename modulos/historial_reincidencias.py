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


def _fecha_ejecucion(planes):
    fechas=[]
    for p in planes:
        try:
            fechas.append(dt.date.fromisoformat(str(p['fecha_ejecucion'])[:10]))
        except (ValueError, KeyError, TypeError):
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
    """Hitos por equipo y modo, respaldados por al menos `minimo` avisos."""
    patrones = sorted(
        [(ev[0].fecha, ev) for _, ev in _patrones(eventos) if len(ev) >= minimo],
        key=lambda item: item[0],
    )
    st.markdown("""<style>
    .hf-history{border-left:3px solid #4c9ed1;margin-left:17px;padding:2px 0 2px 23px}
    .hf-hito{background:rgba(110,145,170,.10);border:1px solid rgba(130,150,170,.25);
       border-radius:14px;padding:16px;margin:0 0 17px;position:relative}
    .hf-hito:before{content:'';position:absolute;left:-34px;top:20px;width:15px;height:15px;
       border-radius:50%;background:#ed873e;border:3px solid #252a30}
    .hf-fecha{font-size:.88rem;font-weight:700;color:#78c1ee}
    .hf-titulo{font-weight:700;font-size:1.05rem;margin:7px 0}
    .hf-texto{line-height:1.5}
    </style>""", unsafe_allow_html=True)
    if not patrones:
        st.info(f"No se identificaron modos de falla con {minimo} o más avisos similares en este período.")
        return
    for _, ev in patrones:
        primero, ultimo = ev[0], ev[-1]
        tp = sum(max(0, float(x.tp_min or 0)) for x in ev)
        texto = (f"Entre el {primero.fecha:%d/%m/%Y} y el {ultimo.fecha:%d/%m/%Y} "
                 f"se registraron {len(ev)} eventos relacionados con «{ultimo.modo}», "
                 f"acumulando {tp:.0f} minutos de tiempo perdido. "
                 f"Síntoma registrado: {_resumen(ev[0])}")
        st.markdown(
            '<div class="hf-history"><div class="hf-hito">'
            f'<div class="hf-fecha">{primero.fecha:%d/%m/%Y} — {ultimo.fecha:%d/%m/%Y}</div>'
            f'<div class="hf-titulo">{html.escape(str(ultimo.equipo_nombre))} · {html.escape(str(ultimo.modo))}</div>'
            f'<div class="hf-texto">{html.escape(texto)}</div>'
            '</div></div>', unsafe_allow_html=True)
        with st.expander(f"Ver los {len(ev)} avisos que respaldan este hito"):
            for e in ev:
                st.markdown(f"**{e.fecha:%d/%m/%Y} · Aviso {e.aviso} · {e.tp_min:g} min TP**")
                st.write(_resumen(e))


def _seguimiento(adfs,avisos,filtrados,ultima):
    st.markdown('#### Efectividad de ADF · Seguimiento de acciones verificadas')
    st.caption('La información se lee directamente desde los planes existentes. No es necesario volver a cargar fechas ni evidencias.')
    visibles=0
    excluidos={'sin_planes':0,'pendientes':0,'sin_vinculo':0,'sin_fecha':0}
    for adf in adfs:
        planes=_planes(adf)
        if not planes:
            excluidos['sin_planes']+=1;continue
        # Estado real de la aplicación: solo "Ejecutado verificado" es un cierre validado.
        if any(p.get('estado_ejecucion')!='Ejecutado verificado' for p in planes):
            excluidos['pendientes']+=1;continue
        origen=[e for e in avisos if e.aviso in _avisos_adf(adf)]
        if not origen:
            excluidos['sin_vinculo']+=1;continue
        if not any(e.aviso in {v.aviso for v in filtrados} for e in origen):continue
        inicio=_fecha_ejecucion(planes)
        if not inicio:
            excluidos['sin_fecha']+=1;continue
        modos={e.modo for e in origen if e.modo and e.modo!='Sin clasificar'}
        if not modos:
            excluidos['sin_vinculo']+=1;continue
        asociados=[e for e in avisos if e.equipo_codigo==origen[0].equipo_codigo and e.modo in modos]
        plazo,confianza,razon=plazo_sugerido([e for e in asociados if e.fecha<=inicio])
        corte=min(ultima,dt.date.today()) if ultima else inicio
        dias=max(0,(corte-inicio).days)
        posteriores=[e for e in asociados if inicio<e.fecha<=corte]
        visibles+=1
        st.markdown(f'**ADF #{adf.id} · {adf.equipo} · {", ".join(sorted(modos))}**')
        st.progress(min(1.,dias/max(plazo,1)))
        st.caption(f'{dias} / {plazo} días observados · {max(0,plazo-dias)} restantes · Confianza {confianza}')
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
    if not visibles:st.info('No hay ADF elegibles con los filtros seleccionados.')
    with st.expander('Diagnóstico: ¿por qué no aparece un ADF?'):
        st.write(f'ADF con planes aún sin ejecutar/verificar: {excluidos["pendientes"]}')
        st.write(f'ADF sin planes estructurados: {excluidos["sin_planes"]}')
        st.write(f'ADF sin aviso SAP coincidente: {excluidos["sin_vinculo"]}')
        st.write(f'ADF sin fecha de ejecución verificada: {excluidos["sin_fecha"]}')
        st.caption('Si el ADF esperado no aparece, revisa el estado real de cada plan y su número de aviso SAP. No se alteraron estados ni validaciones.')


def mostrar_historial_reincidencias():
    usuario=st.session_state.get('usuario_actual') or {}
    if not _autorizado(usuario):
        st.error('No tienes permisos para consultar el historial.');return
    crear_tablas_historial()
    avisos,adfs,excepciones,seguimientos,ultima=datos()
    st.title('📈 Historial de Fallas y Reincidencias')
    st.caption('Historia de equipos · TOP 5 de patrones repetitivos · Seguimiento ADF')
    st.info(f'Historial SAP actualizado hasta {ultima:%d/%m/%Y}' if ultima else 'Todavía no hay avisos SAP importados.')
    filtrados=_filtros_visuales(avisos)
    t1,t2,t3=st.tabs(['🕒 Línea de tiempo','🎯 Oportunidades ADF','📊 Efectividad ADF'])
    with t1:
        st.markdown('#### Historia de fallas recurrentes')
        st.caption('Un hito representa un patrón repetitivo del equipo, no un aviso aislado. '
                   'Las fallas únicas de alto TP siguen disponibles para análisis ADF por separado.')
        minimo=st.selectbox('Mínimo de fallas similares para mostrar un hito',
                            [3,4,5,2],index=0,key='hf_minimo_hitos')
        if filtrados:_timeline(filtrados,minimo=minimo)
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
