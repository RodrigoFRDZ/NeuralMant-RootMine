"""Tablero personal: objetivos, actividades y recomendaciones revisables."""
import io
from datetime import date, datetime
import pandas as pd
import streamlit as st
from database import mi_gestion as db
from database.repositorio_adf import listar_adf

ESTADOS=['Pendiente','En ejecución','Finalizada','Postergada','Descartada']
AVANCE_INICIAL={'Pendiente':0,'En ejecución':10,'Finalizada':100,'Postergada':0,'Descartada':0}

def _dias(fecha):
    try:
        return (date.fromisoformat(str(fecha)[:10])-date.today()).days
    except (ValueError, TypeError):
        return None

def _avance_estado(estado, anterior=0):
    if estado == 'Finalizada': return 100
    if estado in ('Pendiente','Descartada'): return 0
    if estado == 'En ejecución':
        return max(10, min(99, int(anterior or 0))) if int(anterior or 0)>0 else 10
    return max(0, min(99, int(anterior or 0)))

def _panel(registros):
    activos=[r for r in registros if r['tipo'] in ('tarea','compromiso') and r['estado'] not in ('Finalizada','Descartada')]
    vencidas=[r for r in activos if _dias(r.get('fecha_limite')) is not None and _dias(r.get('fecha_limite'))<0]
    proximas=[r for r in activos if _dias(r.get('fecha_limite')) is not None and 0<=_dias(r.get('fecha_limite'))<=7]
    estancadas=[]
    for r in activos:
        try:
            dias=(date.today()-date.fromisoformat(str(r.get('actualizado',''))[:10])).days
            if dias>=15: estancadas.append(r)
        except ValueError: pass
    st.subheader('Panel de control de compromisos')
    a,b,c,d=st.columns(4)
    a.metric('Activos',len(activos));b.metric('Vencidos',len(vencidas));c.metric('Por vencer (7 días)',len(proximas));d.metric('Sin actualización (15 días)',len(estancadas))
    filtro=st.radio('Prioridades', ['Todos','Vencidos','Por vencer','Sin actualización'],horizontal=True,key='gestion_prioridad')
    candidatos={'Todos':activos,'Vencidos':vencidas,'Por vencer':proximas,'Sin actualización':estancadas}[filtro]
    candidatos=sorted(candidatos,key=lambda r:(_dias(r.get('fecha_limite')) is None, _dias(r.get('fecha_limite')) if _dias(r.get('fecha_limite')) is not None else 999999))
    if not candidatos: st.success('No hay compromisos en esta categoría.')
    for r in candidatos:
        dias=_dias(r.get('fecha_limite'))
        alerta=(f'{abs(dias)} días de atraso' if dias is not None and dias<0 else f'Vence en {dias} días' if dias is not None and dias<=7 else 'En plazo' if dias is not None else 'Sin fecha')
        with st.expander(f"{r['titulo']} · {alerta}"):
            st.caption(f"Responsable: {r.get('responsable') or 'Sin asignar'} · Estado: {r['estado']} · Avance: {r.get('avance') or 0}%")
            st.write(f"Última gestión: {r.get('ultima_gestion') or 'Sin registro'}")
            with st.form(f"seguimiento_{r['id']}"):
                nota=st.text_area('Registrar última gestión',value=r.get('ultima_gestion') or '')
                if st.form_submit_button('Guardar seguimiento'):
                    db.actualizar(st.session_state.get('usuario_actual') or {},r['id'],ultima_gestion=nota)
                    st.rerun()
    if activos:
        df=pd.DataFrame([{**r,'dias_para_vencer':_dias(r.get('fecha_limite'))} for r in candidatos])
        st.download_button('📥 Descargar prioridades en Excel',_excel(df),'Prioridades_Mi_Gestion.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key='descargar_prioridades')


def mostrar_mi_gestion():
    usuario=st.session_state.get('usuario_actual') or {}
    if not db.autorizado(usuario):
        st.error('No tienes acceso a este módulo.')
        st.stop()
    db.preparar()
    st.title('🔒 Mi Gestión')
    st.caption('Espacio privado · Objetivos, compromisos, resultados y oportunidades de mejora')
    registros=db.listar(usuario)
    objetivos=[r for r in registros if r['tipo']=='objetivo']
    tareas=[r for r in registros if r['tipo']=='tarea']
    a,b,c,d=st.columns(4)
    a.metric('Objetivos activos',sum(r['estado']!='Finalizada' for r in objetivos))
    b.metric('Tareas pendientes',sum(r['estado'] not in ('Finalizada','Descartada') for r in tareas))
    c.metric('Tareas finalizadas',sum(r['estado']=='Finalizada' for r in tareas))
    d.metric('Objetivos finalizados',sum(r['estado']=='Finalizada' for r in objetivos))
    tab0,tab1,tab2,tab3,tab4=st.tabs(['📊 Resumen ejecutivo','🎯 Objetivos y tareas','📌 Compromisos','✨ Recomendaciones','📈 Resultados y exportación'])
    with tab0:
        _panel(registros)
    with tab1:
        with st.expander('➕ Crear objetivo de mejora'):
            with st.form('nuevo_objetivo'):
                titulo=st.text_input('Fin que se desea alcanzar',placeholder='Mejorar MTBF de freidora')
                objetivo=st.text_area('Justificación / alcance')
                indicador=st.text_input('Indicador',placeholder='MTBF (horas)')
                c1,c2,c3=st.columns(3)
                base=c1.text_input('Línea base'); meta=c2.text_input('Meta'); actual=c3.text_input('Valor actual')
                if st.form_submit_button('Guardar objetivo') and titulo.strip():
                    db.guardar(usuario,'objetivo',titulo.strip(),objetivo,indicador=indicador,linea_base=base,meta=meta,valor_actual=actual)
                    st.rerun()
        for o in objetivos:
            subtareas=[t for t in tareas if t['padre_id']==o['id']]
            completadas=sum(t['estado']=='Finalizada' for t in subtareas)
            avance_total=round(sum(100 if t['estado']=='Finalizada' else 0 if t['estado']=='Pendiente' else int(t.get('avance') or 0) for t in subtareas)/len(subtareas)) if subtareas else 0
            with st.expander(f"🎯 {o['titulo']} · {completadas}/{len(subtareas)} tareas",expanded=False):
                st.write(o['objetivo'] or 'Sin descripción')
                st.caption(f"{o['indicador'] or 'Indicador pendiente'} · Base: {o['linea_base'] or '—'} · Actual: {o['valor_actual'] or '—'} · Meta: {o['meta'] or '—'}")
                st.progress(avance_total/100, text=f'Avance de ejecución: {avance_total}% (no equivale a mejora del indicador)')
                for t in subtareas:
                    c1,c2=st.columns([4,2])
                    c1.markdown(f"**{t['titulo']}**")
                    c1.caption(f"Finalidad: {t['finalidad'] or 'Sin definir'} · Responsable: {t['responsable'] or 'Sin asignar'} · Plazo: {t['fecha_limite'] or 'Sin definir'}")
                    nuevo=c2.selectbox('Estado',ESTADOS,index=ESTADOS.index(t['estado']) if t['estado'] in ESTADOS else 0,key=f"estado_{t['id']}")
                    if nuevo!=t['estado']:
                        db.actualizar(usuario,t['id'],estado=nuevo,avance=_avance_estado(nuevo,t.get('avance') or 0)); st.rerun()
                    if nuevo=='En ejecución':
                        porcentaje=c2.slider('Avance (%)',1,99,max(1,min(99,int(t.get('avance') or 1))),key=f"avance_{t['id']}")
                        if porcentaje != int(t.get('avance') or 0):
                            if c2.button('Guardar avance',key=f"guardar_avance_{t['id']}"):
                                db.actualizar(usuario,t['id'],avance=porcentaje); st.rerun()
                with st.form(f"tarea_{o['id']}"):
                    st.markdown('**Agregar tarea o subtarea**')
                    t=st.text_input('Actividad'); f=st.text_input('¿Para qué se realiza? (finalidad)')
                    resp=st.text_input('Responsable'); plazo=st.date_input('Fecha compromiso',value=None)
                    if st.form_submit_button('Agregar') and t.strip():
                        db.guardar(usuario,'tarea',t.strip(),finalidad=f,padre_id=o['id'],responsable=resp,fecha_limite=plazo.isoformat() if plazo else '')
                        st.rerun()
                with st.form(f"indicador_{o['id']}"):
                    actual=st.text_input('Actualizar indicador actual',value=o['valor_actual'] or '')
                    estado=st.selectbox('Estado del objetivo',ESTADOS,index=ESTADOS.index(o['estado']) if o['estado'] in ESTADOS else 0)
                    if st.form_submit_button('Actualizar objetivo'):
                        db.actualizar(usuario,o['id'],valor_actual=actual,estado=estado);st.rerun()
    with tab2:
        with st.form('compromiso'):
            titulo=st.text_input('Compromiso o gestión')
            finalidad=st.text_input('Finalidad')
            responsable=st.text_input('Responsable')
            fecha=st.date_input('Fecha compromiso',value=None)
            if st.form_submit_button('Registrar compromiso') and titulo.strip():
                db.guardar(usuario,'compromiso',titulo.strip(),finalidad=finalidad,responsable=responsable,fecha_limite=fecha.isoformat() if fecha else '')
                st.rerun()
        for r in registros:
            if r['tipo']!='compromiso':continue
            with st.container(border=True):
                st.write(f"**{r['titulo']}**")
                st.caption(f"Finalidad: {r['finalidad']} · Responsable: {r['responsable']} · Plazo: {r['fecha_limite']}")
                estado=st.selectbox('Estado',ESTADOS,index=ESTADOS.index(r['estado']) if r['estado'] in ESTADOS else 0,key=f"comp_{r['id']}")
                if estado!=r['estado']:
                    db.actualizar(usuario,r['id'],estado=estado,avance=_avance_estado(estado,r.get('avance') or 0));st.rerun()
    with tab3:
        st.info('Las sugerencias requieren tu aprobación. No se crean tareas automáticamente ni se consume IA para generarlas.')
        existentes={r['origen'] for r in registros if r['tipo']=='recomendacion'}
        propuestas=[]
        for a in listar_adf():
            if str(getattr(a,'estado','')).lower()=='borrador':continue
            plan=getattr(a,'plan_prevencion','') or ''
            if plan and plan not in ('[]','{}'):
                propuestas.append((f"ADF #{a.id}",f"Revisar efectividad de acciones del ADF #{a.id} · {a.equipo}",'Comprobar ejecución y resultados de las acciones preventivas'))
            if len(propuestas)>=15:break
        for origen,titulo,finalidad in propuestas:
            if origen in existentes:continue
            with st.container(border=True):
                st.write(f'**{titulo}**');st.caption(finalidad)
                if st.button('Guardar para evaluar',key=f'rec_{origen}'):
                    db.guardar(usuario,'recomendacion',titulo,finalidad=finalidad,origen=origen)
                    st.rerun()
        for r in registros:
            if r['tipo']!='recomendacion':continue
            with st.container(border=True):
                st.write(r['titulo']);st.caption(f"Origen: {r['origen']} · Estado: {r['estado']}")
                c1,c2=st.columns(2)
                if c1.button('Convertir en compromiso',key=f'aceptar_{r["id"]}'):
                    db.guardar(usuario,'compromiso',r['titulo'],finalidad=r['finalidad'],origen=r['origen'])
                    db.actualizar(usuario,r['id'],estado='Finalizada');st.rerun()
                if c2.button('Descartar',key=f'descartar_{r["id"]}'):
                    db.actualizar(usuario,r['id'],estado='Descartada');st.rerun()
    with tab4:
        st.write('**Seguimiento de resultados y evidencias**')
        for o in objetivos:
            st.write(f"{o['titulo']} — {o['indicador']}: {o['linea_base']} → {o['valor_actual']} (meta: {o['meta']})")
        if registros:
            df=pd.DataFrame(registros)
            st.download_button('📥 Descargar Mi Gestión en Excel',data=_excel(df),file_name='Mi_Gestion_RootMine.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

def _excel(df):
    b=io.BytesIO()
    with pd.ExcelWriter(b,engine='openpyxl') as writer:
        if 'tipo' not in df.columns:
            df.to_excel(writer,sheet_name='Prioridades',index=False)
            return b.getvalue()
        for tipo,nombre in [('objetivo','Objetivos'),('tarea','Tareas'),('compromiso','Compromisos'),('recomendacion','Recomendaciones')]:
            df[df['tipo']==tipo].to_excel(writer,sheet_name=nombre,index=False)
    return b.getvalue()
