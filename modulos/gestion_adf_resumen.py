"""Indicadores descriptivos de estados y agrupación orientativa de modos de falla."""
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from database.repositorio_adf import listar_adf

CATEGORIAS=[('Lubricación',('lubric','grasa','aceite','engras')),('Desgaste',('desgast','deterior','abrasion')),('Vibración',('vibrac','desbalance')),('Holgura',('holgura','juego excesivo')),('Temperatura',('temperatura','sobrecalent')),('Fuga',('fuga','filtracion','escape')),('Eléctrica',('cortocircuit','electr','sobrecorriente'))]

def agrupar(texto):
    normal=unicodedata.normalize('NFKD',str(texto or '').lower())
    normal=''.join(c for c in normal if not unicodedata.combining(c))
    grupos=[nombre for nombre,claves in CATEGORIAS if any(c in normal for c in claves)]
    return ' / '.join(grupos) if grupos else 'Sin clasificar'

def mostrar_resumen():
    st.subheader('Seguimiento de ADF y modos de falla')
    st.caption('Agrupación orientativa por palabras clave. Conserva el texto original y requiere revisión técnica.')
    registros=[a for a in listar_adf() if str(getattr(a,'estado','')).lower()!='borrador']
    if not registros:return
    filas=[]
    for a in registros:
        fecha=getattr(a,'fecha_actualizacion',None)
        dias=(datetime.now()-fecha.replace(tzinfo=None)).days if isinstance(fecha,datetime) else None
        filas.append({'ADF':a.id,'Centro':getattr(a,'centro',''),'Área':a.area,'Equipo':a.equipo,
                      'Estado':a.estado,'Creado por':getattr(a,'creado_por',''),
                      'Modo de falla original':a.efecto or '', 'Grupo sugerido':agrupar(a.efecto),
                      'Días desde actualización':dias})
    df=pd.DataFrame(filas)
    st.dataframe(df,use_container_width=True,hide_index=True)
    st.caption('Los días se calculan desde la última actualización; no representan necesariamente el tiempo en manos del liberador.')
    c1,c2=st.columns(2)
    with c1:
        st.write('**ADF por estado**')
        st.bar_chart(df['Estado'].value_counts())
    with c2:
        st.write('**Modos de falla agrupados**')
        st.bar_chart(df['Grupo sugerido'].value_counts())
    st.warning('Para medir tiempos reales de aprobación por liberador se requiere calcularlos desde el historial de validaciones, no desde la fecha de actualización.')
