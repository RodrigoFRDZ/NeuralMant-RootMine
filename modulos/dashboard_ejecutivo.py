"""Panel de gestión ADF y exportación ejecutiva; sin escrituras a BD."""
import io
import json
from collections import Counter, defaultdict
from datetime import date, datetime
import pandas as pd
import streamlit as st
from modulos.agrupacion_fallas import sugerir, normalizar, agrupar_registros


def _fecha(v):
    if isinstance(v, datetime): return v.date()
    if isinstance(v, date): return v
    try: return date.fromisoformat(str(v)[:10])
    except (ValueError, TypeError): return None


def _planes(a):
    try:
        p = getattr(a, 'plan_prevencion', None) or []
        if isinstance(p, str): p=json.loads(p)
        return p if isinstance(p,list) else []
    except (ValueError, TypeError): return []


def _estado_plan(p):
    if not isinstance(p,dict): return 'Pendiente'
    if p.get('estado_ejecucion') in ('Ejecutado','Ejecutado verificado'): return 'Ejecutado'
    fecha=_fecha(p.get('fecha_compromiso'))
    if fecha and fecha<date.today(): return 'Atrasado'
    if fecha and (fecha-date.today()).days<=7: return 'Por vencer'
    return 'Pendiente'


def _tablas(registros, correcciones):
    filas=[]; acciones=[]
    for a in registros:
        original=str(getattr(a,'efecto','') or '')
        grupo=correcciones.get(normalizar(original)) or sugerir(original)
        fecha=_fecha(getattr(a,'fecha_actualizacion',None))
        filas.append({'ADF':getattr(a,'id',''), 'Centro':getattr(a,'centro',''),
            'Área':getattr(a,'area',''), 'Equipo':getattr(a,'equipo',''),
            'Número equipo':getattr(a,'numero_equipo',''), 'Estado':getattr(a,'estado',''),
            'Creado por':getattr(a,'creado_por',''), 'Fecha actualización':str(fecha or ''),
            'Días desde actualización':(date.today()-fecha).days if fecha else None,
            'Modo de falla original':original,'Grupo sugerido':grupo,
            'Tiempo perdido (h)':getattr(a,'tiempo_perdido_h',0) or 0,
            'Conclusión':getattr(a,'conclusion','') or ''})
        for i,p in enumerate(_planes(a),1):
            p=p if isinstance(p,dict) else {'accion':str(p)}
            acciones.append({'ADF':getattr(a,'id',''), 'Área':getattr(a,'area',''),
                'Equipo':getattr(a,'equipo',''),'N° acción':i,'Acción':p.get('accion',''),
                'Responsable':p.get('responsable',''), 'Fecha compromiso':p.get('fecha_compromiso',''),
                'Estado':_estado_plan(p),'Estado registrado':p.get('estado_ejecucion','')})
    return pd.DataFrame(filas),pd.DataFrame(acciones,columns=['ADF','Área','Equipo','N° acción','Acción','Responsable','Fecha compromiso','Estado','Estado registrado'])


def _excel(adf,planes):
    b=io.BytesIO()
    with pd.ExcelWriter(b,engine='openpyxl') as writer:
        total=len(adf); aprobados=int(adf['Estado'].eq('Aprobado').sum()) if total else 0
        resumen=pd.DataFrame([{'ADF totales':total,'Aprobados':aprobados,
            'Pendientes validación':int(adf['Estado'].isin(['Pendiente Supervisor','Pendiente Jefe']).sum()) if total else 0,
            'Porcentaje aprobados':round(100*aprobados/total,1) if total else 0,
            'Planes totales':len(planes),'Planes atrasados':int(planes['Estado'].eq('Atrasado').sum()) if len(planes) else 0}])
        hojas={'Resumen ejecutivo':resumen,'Detalle ADF':adf,
            'Estados ADF':adf.groupby('Estado',dropna=False).size().reset_index(name='Cantidad'),
            'Modos de falla':adf.groupby('Grupo sugerido',dropna=False).agg(ADF=('ADF','count'),Horas=('Tiempo perdido (h)','sum')).reset_index(),
            'Equipos':adf.groupby('Equipo',dropna=False).agg(ADF=('ADF','count'),Horas=('Tiempo perdido (h)','sum')).reset_index(),
            'Areas':adf.groupby('Área',dropna=False).agg(ADF=('ADF','count'),Horas=('Tiempo perdido (h)','sum')).reset_index(),
            'Planes de acción':planes}
        for nombre,df in hojas.items():
            df.to_excel(writer,sheet_name=nombre,index=False)
            ws=writer.sheets[nombre];ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
            for col in ws.columns:
                letter=col[0].column_letter
                ws.column_dimensions[letter].width=min(48,max(13,max(len(str(c.value or '')) for c in list(col)[:150])+2))
    return b.getvalue()


def mostrar_dashboard_ejecutivo(registros):
    st.markdown('## Gestión de ADF y modos de falla')
    st.caption('Indicadores basados en los ADF registrados. Los días desde actualización no equivalen al tiempo real de aprobación.')
    correcciones=st.session_state.setdefault('conocimiento_grupos_revisados',{})
    adf,planes=_tablas(registros,correcciones)
    if adf.empty: return
    estados=adf['Estado'].value_counts()
    c=st.columns(5)
    c[0].metric('ADF analizados',len(adf));c[1].metric('Aprobados',int(estados.get('Aprobado',0)))
    c[2].metric('Pendiente supervisor',int(estados.get('Pendiente Supervisor',0)))
    c[3].metric('Pendiente jefe',int(estados.get('Pendiente Jefe',0)))
    c[4].metric('Requiere corrección',int(estados.get('Requiere corrección',0)))
    c=st.columns(4)
    c[0].metric('Aprobación',f"{100*int(estados.get('Aprobado',0))/len(adf):.1f}%")
    c[1].metric('Modos agrupados',adf['Grupo sugerido'].nunique())
    c[2].metric('Planes de acción',len(planes))
    c[3].metric('Planes atrasados',int(planes['Estado'].eq('Atrasado').sum()) if len(planes) else 0)
    t1,t2,t3,t4=st.tabs(['Estados y pendientes','Modos de falla','Equipos y áreas','Planes y exportación'])
    with t1:
        st.bar_chart(estados)
        pendientes=adf[adf['Estado'].isin(['Pendiente Supervisor','Pendiente Jefe','Requiere corrección'])]
        st.markdown('**ADF pendientes y antigüedad**')
        st.dataframe(pendientes[['ADF','Área','Equipo','Estado','Creado por','Días desde actualización']],hide_index=True,use_container_width=True)
        st.caption('La antigüedad es desde la última actualización, no desde la asignación al liberador.')
    with t2:
        grupos=agrupar_registros(registros,correcciones)
        st.bar_chart(adf['Grupo sugerido'].value_counts().head(15))
        st.caption('“Sin clasificar” conserva descripciones distintas hasta que sean revisadas; no representa un único mecanismo de falla.')
        for grupo,items in grupos.items():
            with st.expander(f'{grupo} · {len(items)} ADF'):
                for a,original in items:
                    st.write(f"ADF #{a.id} · {getattr(a,'equipo','') or 'Sin equipo'} · {original or 'Sin descripción'}")
        originales=sorted(set(adf['Modo de falla original'])-{''})
        if originales:
            st.markdown('**Revisión manual de agrupaciones (solo esta sesión)**')
            original=st.selectbox('Modo original',originales,key='indic_modo_original')
            grupo=st.text_input('Grupo genérico',value=correcciones.get(normalizar(original),sugerir(original)),key='indic_modo_grupo')
            if st.button('Aplicar agrupación',key='indic_aplicar_grupo') and grupo.strip():
                correcciones[normalizar(original)]=grupo.strip()[:120]
                st.rerun()
    with t3:
        st.markdown('**Equipos con más ADF**')
        st.bar_chart(adf['Equipo'].value_counts().head(12))
        st.markdown('**ADF por área**')
        st.bar_chart(adf['Área'].value_counts())
        st.markdown('**Detalle de modos de falla**')
        st.dataframe(adf[['ADF','Área','Equipo','Estado','Modo de falla original','Grupo sugerido','Tiempo perdido (h)']],hide_index=True,use_container_width=True)
    with t4:
        if not planes.empty:
            st.bar_chart(planes['Estado'].value_counts())
            st.dataframe(planes,hide_index=True,use_container_width=True)
        else: st.info('No hay planes de acción para el filtro seleccionado.')
    st.download_button('📥 Descargar informe ejecutivo Excel',data=_excel(adf,planes),
        file_name='RootMine_Indicadores_Ejecutivos.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
    st.caption('Exportación de la selección actual de área. No modifica los ADF ni las tablas de Supabase.')
