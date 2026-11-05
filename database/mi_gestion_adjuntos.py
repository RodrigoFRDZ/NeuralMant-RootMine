"""Evidencias privadas en Supabase Storage (bucket privado preconfigurado)."""
import os
import uuid
import json
import urllib.request
import urllib.error
from urllib.parse import quote

BUCKET = 'mi-gestion-evidencias'

def _secreto(nombre):
    valor = os.environ.get(nombre, '')
    if valor:
        return valor
    try:
        import streamlit as st
        return str(st.secrets.get(nombre, '') or '')
    except Exception:
        return ''

def configurado():
    return bool(_secreto('SUPABASE_URL') and _secreto('SUPABASE_SERVICE_ROLE_KEY'))

def _request(ruta, metodo='GET', data=None, content_type='application/json'):
    base = _secreto('SUPABASE_URL').rstrip('/')
    key = _secreto('SUPABASE_SERVICE_ROLE_KEY')
    if not base or not key:
        raise RuntimeError('Configura SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY en secretos del servidor.')
    req = urllib.request.Request(base + '/storage/v1/' + ruta, data=data, method=metodo,
        headers={'Authorization':'Bearer '+key, 'apikey':key, 'Content-Type':content_type})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError('Error de almacenamiento: '+e.read().decode('utf-8',errors='replace')[:250]) from e

def subir(propietario, item_id, nombre, contenido, tipo):
    extension = nombre.rsplit('.',1)[-1].lower()
    ruta = f'{uuid.uuid5(uuid.NAMESPACE_DNS,propietario).hex}/{int(item_id)}/{uuid.uuid4().hex}.{extension}'
    _request('object/'+BUCKET+'/'+quote(ruta,safe='/'), 'POST', contenido, tipo)
    return ruta

def descargar(ruta):
    return _request('object/'+BUCKET+'/'+quote(ruta,safe='/'))

def eliminar(ruta):
    _request('object/'+BUCKET+'/'+quote(ruta,safe='/'),'DELETE')
