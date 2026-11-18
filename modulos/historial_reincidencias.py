"""Módulo independiente: historial, oportunidades ADF y efectividad."""
from __future__ import annotations
import datetime as dt
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

def mostrar_historial_reincidencias():
    usuario=st.session_state.get('usuario_actual') or {}
    if not _autorizado(usuario):st.error('No tienes permisos para consultar el historial de confiabilidad.');st.stop()
    crear_tablas_historial()
    st.title('📈 Historial de Fallas y Reincidencias')
    st.caption('Equipos críticos A · Avisos SAP · Repetitividad · Efectividad de ADF')
    avisos,adfs,excepciones,seguimientos,ultima=datos()
    st.info(f'Última fecha cubierta por la carga SAP: {ultima:%d/%m/%Y}' if ultima else 'Aún no se ha cargado historial SAP.')
    t1,t2,t3=st.tabs(['🕒 Línea de tiempo','🔎 Oportunidades ADF','✅ Efectividad ADF'])
    with t1:
        filtrados=_filtros(avisos,'hist')
        grupos_eq={}
        for (codigo,modo),eventos in grupos(filtrados).items():
            fila=grupos_eq.setdefault(codigo,{'equipo':eventos[0].equipo_nombre,'area':eventos[0].area,'avisos':0,'tp':0,'prioridad':0})
            fila['avisos']+=len(eventos);fila['tp']+=sum(x.tp_min for x in eventos)
            if len(eventos)>=2:fila['prioridad']+=prioridad(eventos)
        st.subheader('TOP 5 equipos a revisar')
        st.caption('Ranking exploratorio por TP y recurrencia; no equivale a causa raíz confirmada.')
        for i,(codigo,v) in enumerate(sorted(grupos_eq.items(),key=lambda x:(x[1]['prioridad'],x[1]['tp']),reverse=True)[:5],1):
            st.write(f"**{i}. {v['equipo']}** · {codigo} · {v['area']} — {v['avisos']} avisos, {v['tp']:.1f} min TP · prioridad {v['prioridad']:.1f}")
        st.subheader('Línea de tiempo')
        for e in sorted(filtrados,key=lambda x:x.fecha,reverse=True)[:400]:
            vinculados=adfs_vinculados(e,adfs)
            with st.expander(f'{e.fecha:%d/%m/%Y} · {e.equipo_nombre} · {e.descripcion[:80]} · {e.tp_min:g} min'):
                st.write(f'**Aviso:** {e.aviso} · **Equipo SAP:** {e.equipo_codigo} · **Modo sugerido:** {e.modo}')
                st.write(e.texto or 'Sin texto completo')
                st.write('ADF relacionados (coincidencia por equipo o aviso): '+(', '.join(str(a.id) for a in vinculados) if vinculados else 'No identificados'))
        if len(filtrados)>400:st.warning('Se muestran los 400 avisos más recientes; utiliza filtros para reducir la selección.')
    with t2:
        filtrados=_filtros(avisos,'oport')
        candidatos=[]
        for (codigo,modo),eventos in grupos(filtrados).items():
            eventos=sorted(eventos,key=lambda x:x.fecha)
            if not eventos:continue
            area=eventos[-1].area.upper()
            limite=30 if 'FAENA' in area else 60
            obligatorios=[e for e in eventos if e.tp_min>limite]
            if obligatorios or len(eventos)>=2:candidatos.append((prioridad(eventos),codigo,modo,eventos,obligatorios))
        st.caption('Umbrales: Faena >30 min; otras áreas >60 min. Una causa aparente conocida no elimina automáticamente la exigencia de ADF.')
        for punt,codigo,modo,eventos,obligatorios in sorted(candidatos,reverse=True)[:100]:
            with st.expander(f"{eventos[-1].equipo_nombre} · {modo} · {len(eventos)} eventos · {sum(x.tp_min for x in eventos):.1f} min TP"):
                st.write(f'{len(obligatorios)} avisos superan el umbral de TP · Prioridad exploratoria: {punt}')
                st.write('Avisos: '+', '.join(e.aviso for e in eventos))
                relacionados={a.id for e in eventos for a in adfs_vinculados(e,adfs)}
                st.write('ADF vinculados: '+(', '.join(map(str,sorted(relacionados))) if relacionados else 'No identificados'))
                st.caption('Clasificación por reglas: verificar que los avisos tengan el mismo modo y causa antes de confirmar reincidencia.')
                if st.button('Preparar nuevo ADF',key=f'crear_{codigo}_{modo}'):
                    st.session_state['historial_preparar_adf']={'numero_equipo':codigo,'equipo':eventos[-1].equipo_nombre,'avisos':[e.aviso for e in eventos],'fenomeno':modo}
                    st.session_state['pagina']='📝 RootMine · Nuevo ADF'
                    st.warning('Antecedentes disponibles en session_state["historial_preparar_adf"]. El formulario ADF debe integrar explícitamente esta precarga; no se creó un ADF automáticamente.')
                if _admin(usuario):
                    aviso=st.selectbox('Justificar excepción del aviso',['Seleccionar']+[e.aviso for e in eventos],key=f'ex_{codigo}_{modo}')
                    if aviso!='Seleccionar':
                        with st.form(f'form_ex_{aviso}_{codigo}_{modo}'):
                            causa=st.text_area('Causa aparente conocida')
                            just=st.text_area('Justificación de no realizar ADF')
                            accion=st.text_area('Acción correctiva / preventiva aplicada')
                            if st.form_submit_button('Guardar justificación'):
                                if not causa.strip() or not just.strip():st.error('Completa causa y justificación.')
                                else:
                                    with Session(engine) as s:
                                        registro=s.get(ExcepcionADF,aviso)
                                        if registro is None:registro=ExcepcionADF(aviso=aviso,causa=causa,justificacion=just,accion=accion,responsable=usuario.get('correo',''))
                                        else:registro.causa=causa;registro.justificacion=just;registro.accion=accion;registro.responsable=usuario.get('correo','');registro.fecha=dt.datetime.utcnow()
                                        s.add(registro);s.commit()
                                    st.success('Excepción documentada. No se eliminó la obligación normativa por TP.')
    with t3:
        filtrados=_filtros(avisos,'efect')
        codigos={e.equipo_codigo for e in filtrados}
        candidatos=[a for a in adfs if str(a.numero_equipo or '') in codigos] if avisos else []
        estados=['Todos','Planes sin completar','Planes pendientes','Pendiente de seguimiento','En observación','Posible reincidencia','Evidencia insuficiente','Efectividad validada']
        estado_filtro=st.selectbox('Estado de efectividad',estados)
        for a in candidatos:
            relacionados=[e for e in avisos if e.equipo_codigo==a.numero_equipo]
            seg=seguimientos.get(a.id)
            estado,razon=estado_efectividad(a,relacionados,seg,ultima)
            if estado_filtro!='Todos' and estado!=estado_filtro:continue
            icono='✅' if estado=='Efectividad validada' else '⚠️' if estado=='Posible reincidencia' else '🕒'
            with st.expander(f'{icono} ADF #{a.id} · {a.equipo} · {estado}'):
                st.write(razon)
                plazo,confianza,justificacion=plazo_sugerido([e for e in relacionados if e.modo!='Sin clasificar'])
                st.write(f'**Plazo sugerido:** {plazo} días · Confianza {confianza}. {justificacion}')
                st.caption('El plazo es una estimación y no demuestra por sí solo la eliminación de la causa.')
                if _admin(usuario):
                    with st.form(f'seg_{a.id}'):
                        dias=st.number_input('Plazo automático sugerido (días)',min_value=1,max_value=1095,value=seg.plazo_dias if seg else plazo,disabled=True)
                        inicio=st.date_input('Fecha de ejecución y verificación de la última acción causal',value=seg.inicio if seg and seg.inicio else None)
                        evidencia=st.text_area('Evidencia técnica de control y exposición (no basta ausencia de avisos)',value=seg.evidencia_validada if seg else '')
                        if st.form_submit_button('Registrar inicio de seguimiento'):
                            if not inicio:st.error('Indica la fecha real de ejecución.')
                            else:
                                with Session(engine) as s:
                                    reg=s.get(SeguimientoADF,a.id)
                                    if reg is None:reg=SeguimientoADF(adf_id=a.id,plazo_dias=plazo,fundamento=justificacion,confianza=confianza,inicio=inicio,evidencia_validada=evidencia)
                                    else:reg.plazo_dias=plazo;reg.fundamento=justificacion;reg.confianza=confianza;reg.inicio=inicio;reg.evidencia_validada=evidencia;reg.calculado_en=dt.datetime.utcnow()
                                    s.add(reg);s.commit()
                                st.success('Seguimiento registrado. Actualiza la página para recalcular.')

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
