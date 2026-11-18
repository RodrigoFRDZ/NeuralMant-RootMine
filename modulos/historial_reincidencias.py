"""Módulo independiente: historial, oportunidades ADF y efectividad."""
from __future__ import annotations
import datetime as dt
import json
import re
import streamlit as st
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

def _planes_listos(adf):
    try: planes=json.loads(adf.plan_prevencion or '[]')
    except (ValueError,TypeError):return None
    if not isinstance(planes,list) or not planes:return None
    if any(not isinstance(p,dict) or p.get('estado_ejecucion')!='Ejecutado verificado' for p in planes):return None
    try:return max(dt.date.fromisoformat(str(p['fecha_ejecucion'])[:10]) for p in planes)
    except (ValueError,KeyError,TypeError):return None

def _avisos_adf(adf):
    return set(re.findall(r'\d{7,}',str(adf.aviso_sap or '')))

def _similares(avisos):
    grupos_validos={}
    for clave, eventos in grupos(avisos).items():
        if clave[1] != 'Sin clasificar' and len(eventos)>=2:
            grupos_validos[clave]=sorted(eventos,key=lambda e:e.fecha)
    return grupos_validos

def _resumen(e):
    texto=' '.join((e.descripcion or '').split())
    detalle=' '.join((e.texto or '').split())
    if detalle and detalle.lower() not in texto.lower():texto+=' — '+detalle
    return texto[:210]+('…' if len(texto)>210 else '')

def mostrar_historial_reincidencias():
    usuario=st.session_state.get('usuario_actual') or {}
    if not _autorizado(usuario):st.error('No tienes permisos para consultar el historial.');return
    crear_tablas_historial()
    st.subheader('Historial de Fallas y Reincidencias')
    avisos,adfs,excepciones,seguimientos,ultima=datos()
    st.info(f'Historial SAP actualizado hasta {ultima:%d/%m/%Y}' if ultima else 'Aún no hay avisos importados.')
    filtrados=_filtros(avisos,'hist')
    t1,t2,t3=st.tabs(['🕒 Línea de tiempo','🎯 Oportunidades ADF','✅ Efectividad ADF'])
    with t1:
        st.markdown('#### Línea de tiempo por equipo')
        st.caption('Todos los eventos del período seleccionado, incluidos los no repetitivos.')
        if not filtrados:st.info('No hay eventos para este filtro.')
        for e in sorted(filtrados,key=lambda v:(v.fecha,v.aviso),reverse=True):
            st.markdown(f'**{e.fecha:%d/%m/%Y} · {e.equipo_nombre} · {e.tp_min:g} min TP**')
            st.caption(f'Aviso {e.aviso} · {e.modo}')
            st.write(_resumen(e))
            with st.expander('Texto completo y ADF asociado'):
                st.write(e.texto or 'Sin texto completo')
                vinculados=[a for a in adfs if e.aviso in _avisos_adf(a)]
                st.write('ADF: '+(', '.join(str(a.id) for a in vinculados) if vinculados else 'No vinculado por aviso'))
            st.divider()
    with t2:
        st.markdown('#### TOP 5 · Oportunidades de ADF')
        st.caption('Solo eventos similares por equipo y categoría de falla. Las coincidencias requieren revisión técnica.')
        candidatos=[]
        for clave,eventos in _similares(filtrados).items():
            # Un ADF del mismo equipo NO basta para ocultar una causa distinta.
            if any(e.aviso in _avisos_adf(a) for e in eventos for a in adfs):continue
            candidatos.append((prioridad(eventos),eventos))
        candidatos.sort(key=lambda t:t[0],reverse=True)
        if not candidatos:st.success('No se detectan patrones repetitivos pendientes en el filtro.')
        for i,(punt,eventos) in enumerate(candidatos[:5],1):
            primero,ultimo=eventos[0],eventos[-1]
            st.markdown(f'**{i}. {ultimo.equipo_nombre} · {ultimo.modo}**')
            c1,c2,c3=st.columns(3)
            c1.metric('Fallas',len(eventos));c2.metric('TP acumulado',f'{sum(e.tp_min for e in eventos):.0f} min')
            c3.metric('Período',f'{(ultimo.fecha-primero.fecha).days} días')
            st.progress(min(1.,punt/100))
            with st.expander('Revisar eventos similares'):
                for e in eventos:st.write(f'{e.fecha:%d/%m/%Y} · {e.aviso} · {_resumen(e)}')
            if st.button('Validar oportunidad / preparar ADF',key=f'crear_{ultimo.equipo_codigo}_{ultimo.modo}'):
                st.session_state['historial_preparar_adf']={'numero_equipo':ultimo.equipo_codigo,'equipo':ultimo.equipo_nombre,'avisos':[e.aviso for e in eventos],'fenomeno':ultimo.modo}
                st.warning('Antecedentes preparados. Falta conectar la precarga al formulario ADF; no se creó ningún análisis.')
            st.divider()
    with t3:
        st.markdown('#### Seguimiento automático de efectividad')
        st.caption('Solo ADF con todos sus planes ejecutados y verificados, fecha real de ejecución y aviso SAP vinculado.')
        visibles=0
        for a in adfs:
            inicio=_planes_listos(a)
            if not inicio:continue
            origen=[e for e in avisos if e.aviso in _avisos_adf(a)]
            if not origen or not any(e.aviso in {v.aviso for v in filtrados} for e in origen):continue
            modos={e.modo for e in origen if e.modo!='Sin clasificar'}
            if not modos:continue
            relacionados=[e for e in avisos if e.equipo_codigo==a.numero_equipo and e.modo in modos]
            historicos=[e for e in relacionados if e.fecha<=inicio]
            plazo,confianza,razon=plazo_sugerido(historicos)
            corte=min(ultima,dt.date.today()) if ultima else inicio
            dias=max(0,(corte-inicio).days)
            posteriores=[e for e in relacionados if inicio<e.fecha<=corte]
            visibles+=1
            st.markdown(f'**ADF #{a.id} · {a.equipo} · {", ".join(sorted(modos))}**')
            st.progress(min(1.,dias/max(plazo,1)))
            st.caption(f'{dias} de {plazo} días · {max(0,plazo-dias)} restantes · Confianza {confianza}')
            if posteriores:
                st.error(f'⚠️ {len(posteriores)} posible(s) reincidencia(s): confirmar misma causa antes de declarar no efectivo.')
                with st.expander('Nuevos antecedentes'):
                    for e in posteriores:st.write(f'{e.fecha:%d/%m/%Y} · Aviso {e.aviso} · {_resumen(e)}')
                    if st.button('Preparar reapertura de ADF',key=f'reabrir_{a.id}'):
                        st.session_state['historial_reapertura_propuesta']={'adf_id':a.id,'avisos':[e.aviso for e in posteriores]}
                        st.warning('Propuesta registrada en esta sesión. No se modificó ni reabrió el ADF; requiere integración con el flujo de aprobación.')
            elif dias<plazo:st.info('🕒 En observación; sin fallas similares en los datos cargados.')
            elif confianza in ('baja','muy baja'):st.warning('Plazo cumplido, pero evidencia histórica insuficiente para validar efectividad.')
            else:st.success('✓ Plazo cumplido sin eventos similares detectados. Efectividad preliminar: verificar exposición y controles.')
            with st.expander('Fundamento del plazo'):st.write(razon)
            st.divider()
        if not visibles:st.info('No hay ADF elegibles con los filtros actuales.')

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
