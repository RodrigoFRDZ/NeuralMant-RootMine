"""Editorial presentation only; original supervisor records remain unchanged."""
import re
import unicodedata


def _clave(texto):
    return ''.join(c for c in unicodedata.normalize('NFD',texto.lower()) if not unicodedata.combining(c)).strip(' .,;:')


def corregir(texto,contexto=''):
    texto=str(texto or '').strip()
    # This substitution is justified only by an explicit reference to ice.
    if re.search(r'\bhielo\b',_clave(contexto)):
        texto=re.sub(r'\bhuelo\b','hielo',texto,flags=re.I)
    texto=re.sub(r'\bcamara\b','cámara',texto,flags=re.I)
    texto=re.sub(r'\bquedo(?=\s+(?:un poco|hielo|en los|en las))','quedó',texto,flags=re.I)
    texto=re.sub(r'\bse logro\b','se logró',texto,flags=re.I)
    texto=re.sub(r'\s+([,.;:])',r'\1',texto)
    return texto


def consolidar(textos,contexto=''):
    """Merge repeated observations and generated wrappers without truncation."""
    partes=[];claves=[]
    for texto in textos:
        for parte in re.split(r'\s*[|·\n]\s*|(?<=[.!?])\s+',corregir(texto,contexto)):
            parte=re.sub(r'^Observación (?:en pruebas|durante la prueba):\s*','',parte,flags=re.I).strip()
            if not parte:continue
            clave=_clave(parte)
            clave=re.sub(r'^(?:el supervisor informa que |la observacion )','',clave)
            if clave in claves:continue
            partes.append(parte[0].upper()+parte[1:]);claves.append(clave)
    return ' '.join(p if p.endswith(('.', '!', '?')) else p+'.' for p in partes)


def detalle_seguimiento(d):
    """Weekly observations exclude unrelated delay history shown separately."""
    contexto=d.get('descripcion','')
    textos=[d.get('detalle_prueba',''),d.get('hallazgos','')]
    from motores.foco_partida import senales
    for h in d.get('historial',[]):
        texto=h.get('mensaje','')
        if not h.get('automatico') and 'Operación' in senales(texto):textos.append(texto)
    if 'Operación' in senales(d.get('ultimo_mensaje','')):textos.append(d['ultimo_mensaje'])
    return consolidar(textos,contexto)
