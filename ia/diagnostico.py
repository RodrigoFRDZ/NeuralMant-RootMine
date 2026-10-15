"""Diagnóstico breve de fallos de resumen, sin claves ni entradas de validación."""
import json
import logging
import re
from datetime import datetime,timezone
from uuid import uuid4
from pydantic import ValidationError
from ia.cliente import obtener_configuracion,mensaje_amigable_ia


def diagnosticar_resumen(error):
    configuracion=obtener_configuracion()
    if isinstance(error,ValidationError):
        detalle=json.dumps(error.errors(include_input=False,include_context=False,include_url=False),ensure_ascii=False,default=str)
    else:detalle=str(error) or 'El proveedor no entregó una descripción del fallo.'
    clave=configuracion.api_key
    if clave:detalle=detalle.replace(clave,'[CLAVE OCULTA]')
    detalle=re.sub(r'AIza[0-9A-Za-z_-]{20,}','[CLAVE OCULTA]',detalle)
    detalle=re.sub(r'(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*',r'\1[OCULTO]',detalle)
    detalle=re.sub(r'''(?i)((?:api[_-]?key|access[_-]?token|password|secret)\s*["']?\s*[:=]\s*["']?)[^\s,}\]"'&]+''',r'\1[OCULTO]',detalle)
    detalle=detalle[:2400]
    orientacion=mensaje_amigable_ia(error)
    if not orientacion:
        texto=detalle.lower()
        if 'no existe gemini_api_key' in texto:orientacion='Falta configurar la clave central de GearBot.'
        elif 'bitácora demasiado extensa' in texto:orientacion='La bitácora supera el tamaño admitido para esta revisión con IA.'
        elif isinstance(error,ValidationError):orientacion='La respuesta de la IA no cumplió el formato requerido para el informe.'
        elif any(x in texto for x in ('api_key_invalid','api key not valid','unauthenticated','permission_denied')):orientacion='El proveedor rechazó la autenticación o los permisos de la clave.'
        elif any(x in texto for x in ('model not found','model is not found','is not found for api version')):orientacion='El modelo configurado no está disponible para esta consulta.'
        elif isinstance(error,TimeoutError) or any(x in texto for x in ('timed out','timeout','connectionerror','connection refused')):orientacion='La conexión con el proveedor de IA falló o excedió el tiempo de espera.'
        else:orientacion='No fue posible completar el análisis con IA. Administración puede revisar el detalle del fallo.'
    resultado=dict(referencia=uuid4().hex[:10],fecha=datetime.now(timezone.utc).isoformat(),tipo=type(error).__name__,modelo=configuracion.modelo,detalle=detalle,mensaje=orientacion)
    logging.getLogger('neuralmant.ia.resumen').error('GearBot resumen ref=%s fecha=%s tipo=%s modelo=%s detalle=%s',resultado['referencia'],resultado['fecha'],resultado['tipo'],resultado['modelo'],detalle)
    return resultado
