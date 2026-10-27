"""Agrupación conservadora y revisable de fenómenos, sin modificar ADF."""
import re
import unicodedata
from collections import defaultdict

# Categorías técnicas basadas en objeto + mecanismo; no mezclar mecanismos diferentes.
REGLAS = [
    ("Correas · rotura", ("correa", "banda"), ("rotur", "rota", "roto", "cortad", "partid", "quebrad")),
    ("Correas · deslizamiento", ("correa", "banda"), ("patin", "desliz")),
    ("Correas · desgaste", ("correa", "banda"), ("desgast", "deterior")),
    ("Rodamientos · daño", ("rodamiento", "cojinete", "ruleman"), ("fall", "averi", "danad", "gripad", "trabado", "fatiga")),
    ("Rodamientos · desgaste", ("rodamiento", "cojinete", "ruleman"), ("desgast", "deterior")),
    ("Rodamientos · temperatura", ("rodamiento", "cojinete", "ruleman"), ("calent", "temperatura", "sobrecalent")),
    ("Sellos · fugas", ("sello", "reten", "empaquetadura"), ("fuga", "filtr", "perdid", "escape")),
    ("Tuberías · fugas", ("tuberia", "caneria", "ducto"), ("fuga", "filtr", "perdid", "escape")),
    ("Motores · falla eléctrica", ("motor",), ("cortocircuit", "bobinad", "aislamient", "sobrecorriente")),
    ("Motores · temperatura", ("motor",), ("calent", "temperatura", "sobrecalent")),
]

# Clasificación por mecanismo principal, aplicable aunque el texto no nombre
# explícitamente el componente. Prioridad deliberada para evitar categorías duplicadas.
MECANISMOS = [
    ("Fallas eléctricas", ("cortocircuit", "corto circuito", "electrica", "electrico", "bobinad", "sobrecorriente", "aislamiento", "etapa de potencia", "fusible")),
    ("Fallas de comunicación y control", ("comunicacion", "following error", "seguimiento", "control", "sensor", "encoder", "plc", "senal")),
    ("Fugas y filtraciones", ("fuga", "filtracion", "escape de", "perdida de fluido")),
    ("Desgaste y corrosión", ("corrosion", "desgaste", "abrasiv", "erosion", "deterioro")),
    ("Desalineación e interferencias", ("desaline", "interferencia", "atascamiento", "jamming", "cuerpo extrano", "pitch mismatch")),
    ("Vibración y desbalance", ("vibracion", "desbalance", "vibra")),
    ("Fatiga y rotura mecánica", ("fatiga", "fractura", "rotura", "quiebre", "deformacion plastica")),
    ("Sobrecalentamiento", ("sobrecalent", "temperatura", "termica", "calentamiento")),
    ("Sobrecarga mecánica", ("sobrecarga", "sobre esfuerzo", "sobreesfuerzo")),
    ("Lubricación", ("lubric", "engrase", "grasa", "falta de aceite")),
]

def normalizar(valor):
    valor = unicodedata.normalize("NFKD", str(valor or "").lower())
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", valor)).strip()

def sugerir(texto):
    limpio = normalizar(texto)
    if not limpio:
        return "Sin agrupar"
    candidatos = [nombre for nombre, objetos, mecanismos in REGLAS
                  if any(o in limpio for o in objetos) and any(m in limpio for m in mecanismos)]
    if len(candidatos) == 1:
        return candidatos[0]
    # Clasificar por mecanismo predominante. No constituye diagnóstico técnico.
    for nombre, palabras in MECANISMOS:
        if any(p in limpio for p in palabras):
            return nombre
    return "Sin agrupar"

def agrupar_registros(registros, reemplazos=None):
    grupos = defaultdict(list)
    reemplazos = reemplazos or {}
    for adf in registros:
        original = str(getattr(adf, "efecto", "") or "").strip()
        grupo = reemplazos.get(normalizar(original)) or sugerir(original)
        grupos[grupo].append((adf, original))
    return dict(sorted(grupos.items(), key=lambda par: (-len(par[1]), par[0])))
