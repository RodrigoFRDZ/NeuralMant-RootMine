"""Conservative report signals from saved observations; never operational approval."""
import re,unicodedata
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
CATEGORIAS=['Automática','Seguridad','Calidad','Retraso','Trabajo no informado','Operación','General']
IMPACTOS=['Por evaluar','Partida','Operación semanal','Partida y operación semanal','Sin impacto informado']
def normalizar(t):return ''.join(c for c in unicodedata.normalize('NFD',str(t).lower()) if not unicodedata.combining(c))
def senales(t):
    t=normalizar(t)
    # Remove explicit negative statements before matching words, not the entire observation.
    t=re.sub(r'\b(?:sin|no (?:hay|hubo|presenta|se evidenciaron))\s+(?:observaciones|retrasos?|atrasos?|riesgos?|fugas?|vibraciones?|ruidos?|problemas de calidad)\b','',t)
    resultado=[]
    for categoria,patron in [('Seguridad',r'seguridad|atrapamiento|sin resguardo|sin proteccion|riesgo de|accidente'),('Calidad',r'calidad|inocuidad|contamin|cuerpo extrano|producto expuesto'),('Retraso',r'retras|atras|fuera de plazo|(?:entreg|termin|finaliz)\w*[^.!?\n]{0,70}\b(?:tarde|fuera de horario)'),('Trabajo no informado',r'no (?:estaba|esta|fue) (?:informad|programad)|no informado|no programado|fuera del programa|no corresponde|no estaba contemplad|fuera del alcance')]:
        if re.search(patron,t):resultado.append(categoria)
    if re.search(r'vibracion|ruido|fuga|recalent|sobretemperatura|holgura|falla recurrente|funcionamiento inestable|no funciona|no esta apt|preocup|impide[^.!?]{0,40}partida|afecta[^.!?]{0,40}partida',t):resultado.append('Operación')
    return resultado

def clasificar(texto,categoria='Automática',impacto='Por evaluar'):
    if categoria not in CATEGORIAS or impacto not in IMPACTOS:raise ValueError('Categoría o impacto inválido.')
    detectadas=senales(texto)
    return dict(categoria=(detectadas[0] if detectadas else 'General') if categoria=='Automática' else categoria,
        impacto=impacto,clasificacion='Orientativa por texto' if categoria=='Automática' else 'Informada por supervisor')

def focos(filas,novedades=()):
    partida=[];semana=[];retrasos=[]
    for d in filas:
        ref=f"{d['descripcion']} · {d['area']}"
        razones=[]
        if d['estado']=='Detenido':razones.append('Trabajo detenido: '+(d.get('pendiente') or 'Motivo por revisar'))
        elif d.get('pendiente'):razones.append('Pendiente registrado: '+d['pendiente'])
        if d['prueba']=='Fallida':razones.append('Prueba fallida: '+(d.get('detalle_prueba') or 'Resultado por revisar'))
        elif d['estado']=='Terminado' and d['prueba'] not in ('Aprobada','No requerida'):razones.append('Ejecución terminada, prueba de funcionamiento pendiente.')
        actuales=' | '.join(dict.fromkeys(str(d.get(k) or '') for k in ('hallazgos','pendiente','ultimo_mensaje','detalle_prueba') if d.get(k)))
        antecedentes=[h['mensaje'] for h in d.get('historial',[]) if h.get('mensaje') and not h.get('automatico') and senales(h['mensaje'])]
        antecedentes_texto=' | '.join(dict.fromkeys(t for t in antecedentes if t not in actuales))
        actual_senales=senales(actuales+' '+antecedentes_texto)
        if set(actual_senales)&{'Seguridad','Calidad'}:razones.append('Antecedente de seguridad/calidad: '+(actuales+' '+antecedentes_texto)+'. Verificar vigencia y tratamiento.')
        if razones:partida.append(dict(referencia=ref,detalle=' '.join(razones),accion='Propuesta: verificar en terreno y definir la condición de entrega antes de la partida.'))
        if 'Operación' in actual_senales:semana.append(dict(referencia=ref,detalle=(actuales+' '+antecedentes_texto),accion='Propuesta: evaluar la observación y acordar seguimiento durante la semana.'))
        mensajes=[h['mensaje'] for h in d.get('historial',[]) if h.get('mensaje') and not h.get('automatico')]
        tardias=[t for t in mensajes if 'Retraso' in senales(t)]
        if tardias:retrasos.append(dict(referencia=ref,detalle='Retraso / entrega tardía informada: '+' | '.join(tardias),accion='Validar la hora real de entrega y su efecto en la partida. No se calcula una demora sin horario confirmado.'))
    for a in novedades:
        if a.get('estado')!='Abierto' or a.get('resuelve'):continue
        f=dict(referencia=a['categoria']+' · '+a['area'],detalle=a['categoria']+': '+a['mensaje'],accion='Propuesta: coordinar revisión del hallazgo y registrar el tratamiento o resolución.')
        texto=normalizar(a['mensaje'])
        if a['categoria'] in ('Seguridad','Calidad','Retraso','Trabajo no informado','Operación') or set(senales(texto))&{'Seguridad','Calidad'} or re.search(r'partida|arranque|puesta en marcha',texto):partida.append(f)
        if a['categoria']=='Operación' or 'Operación' in senales(texto) or re.search(r'durante la semana|operacion semanal',texto):semana.append(f)
        if a['categoria']=='Retraso':retrasos.append(f)
    return dict(partida=partida,semana=semana,retrasos=retrasos)
