"""Shared natural conversation for functional testing, online and offline."""
import re
import unicodedata

PREGUNTAS={'observaciones':'¿Cómo resultaron las pruebas? ¿Se observó alguna anomalía durante el proceso?',
 'descripcion':'Describe qué observaste durante la prueba.',
 'impacto':'¿Esta observación impide la partida o el funcionamiento normal del equipo?'}

def normalizar(texto):
    t=unicodedata.normalize('NFKD',texto.lower().strip())
    return re.sub(r'[^a-z0-9 ]','', ''.join(c for c in t if not unicodedata.combining(c))).strip()

def transicion(d,accion,texto=''):
    nuevo={k:d[k] for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba')}
    dialogo=dict(d.get('dialogo_prueba') or {})
    paso=dialogo.get('paso')
    if d['estado']!='Terminado':raise ValueError('Registra primero la finalización del trabajo antes de realizar su prueba de funcionamiento.')
    if accion=='iniciar_prueba':
        if d['prueba']=='Aprobada':raise ValueError('La prueba ya está registrada como satisfactoria.')
        nuevo.update(prueba='En prueba',detalle_prueba='El supervisor informa que se realizaron las pruebas. Resultado y observaciones pendientes de registrar.')
        dialogo={'paso':'observaciones'}
    elif accion=='sin_observaciones':
        if paso!='observaciones':raise ValueError('Primero indica que se realizaron las pruebas.')
        nuevo.update(prueba='Aprobada',detalle_prueba='Prueba de funcionamiento satisfactoria. El supervisor informa funcionamiento normal y sin observaciones.')
        dialogo={'paso':'','resultado':'Sin observaciones'}
    elif accion=='con_observaciones':
        if paso!='observaciones':raise ValueError('La conversación de pruebas cambió. Revisa el estado actual.')
        dialogo['paso']='descripcion'
    elif accion=='describir_observacion':
        if paso not in ('observaciones','descripcion'):raise ValueError('Primero registra el resultado de la prueba.')
        if len(texto.strip())<4:raise ValueError('Describe la observación con más detalle.')
        observacion=texto.strip()
        nuevo.update(prueba='En prueba',detalle_prueba='Observación durante la prueba: '+observacion+' · Impacto en partida pendiente de aclarar.')
        nuevo['hallazgos']=(d['hallazgos']+'\n' if d['hallazgos'] else '')+'Observación en pruebas: '+observacion
        dialogo={'paso':'impacto','observacion':observacion}
    elif accion in ('impide_partida','no_impide_partida'):
        if paso!='impacto' or not dialogo.get('observacion'):raise ValueError('Describe primero la observación durante la prueba.')
        impide=accion=='impide_partida'
        nuevo.update(prueba='Fallida' if impide else 'Aprobada',detalle_prueba='Observación durante la prueba: '+dialogo['observacion']+' · El supervisor informa que '+('impide la partida.' if impide else 'no impide la partida ni el funcionamiento normal.'))
        dialogo.update(paso='',impide_partida=impide)
    else:raise ValueError('Acción de pruebas no reconocida.')
    nuevo['dialogo_prueba']=dialogo
    return nuevo

def desde_mensaje(d,mensaje):
    if d['estado']!='Terminado':return None
    paso=(d.get('dialogo_prueba') or {}).get('paso');t=normalizar(mensaje)
    if '%' in mensaje or t in ('trabajo terminado','trabajo finalizado','trabajo completado','iniciado'):return None
    if paso=='observaciones':
        if t in ('no','sin observaciones','no hubo observaciones','ninguna','no se observaron anomalias','no se evidenciaron observaciones','todo bien','funcionamiento normal sin observaciones','sin anomalias'):
            return transicion(d,'sin_observaciones')
        if t in ('si','con observaciones','hubo observaciones'):return transicion(d,'con_observaciones')
        if len(t)>5 and not t.isdigit():return transicion(d,'describir_observacion',mensaje)
    if paso=='descripcion' and len(t)>5:return transicion(d,'describir_observacion',mensaje)
    if paso=='impacto':
        if t in ('si','si impide','impide la partida','impide el funcionamiento'):return transicion(d,'impide_partida')
        if t in ('no','no impide','no impide la partida','no impide el funcionamiento'):return transicion(d,'no_impide_partida')
    return None
