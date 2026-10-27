"""Agrupación conservadora y revisable de fenómenos, sin modificar ADF."""
import re
import unicodedata
from collections import defaultdict

# Categorías técnicas basadas en objeto + mecanismo; no mezclar mecanismos diferentes.
REGLAS = [
    ("Correa · rotura", ("correa", "banda"), ("rotur", "rota", "roto", "cortad", "partid", "quebrad")),
    ("Correa · deslizamiento", ("correa", "banda"), ("patin", "desliz")),
    ("Correa · desgaste", ("correa", "banda"), ("desgast", "deterior")),
    ("Rodamiento · falla", ("rodamiento", "cojinete", "ruleman"), ("fall", "averi", "danad", "gripad", "trabado")),
    ("Rodamiento · desgaste", ("rodamiento", "cojinete", "ruleman"), ("desgast", "deterior")),
    ("Rodamiento · temperatura", ("rodamiento", "cojinete", "ruleman"), ("calent", "temperatura", "sobrecalent")),
    ("Sello · fuga", ("sello", "reten", "empaquetadura"), ("fuga", "filtr", "perdid", "escape")),
    ("Tubería · fuga", ("tuberia", "caneria", "ducto"), ("fuga", "filtr", "perdid", "escape")),
    ("Motor · falla eléctrica", ("motor",), ("cortocircuit", "bobinad", "aislamient", "sobrecorriente")),
    ("Motor · temperatura", ("motor",), ("calent", "temperatura", "sobrecalent")),
    ("Equipo · vibración", ("vibracion", "vibra", "desbalance"), ("vibracion", "vibra", "desbalance")),
    ("Equipo · lubricación", ("lubric", "grasa", "engrase"), ("lubric", "grasa", "engrase")),
]

def normalizar(valor):
    valor = unicodedata.normalize("NFKD", str(valor or "").lower())
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", valor)).strip()

def sugerir(texto):
    limpio = normalizar(texto)
    if not limpio:
        return "Sin descripción"
    candidatos = [nombre for nombre, objetos, mecanismos in REGLAS
                  if any(o in limpio for o in objetos) and any(m in limpio for m in mecanismos)]
    if len(candidatos) == 1:
        return candidatos[0]
    if len(candidatos) > 1:
        return "Revisión técnica requerida"
    # Agrupar variantes estrictamente iguales tras normalizar, no por similitud vaga.
    return "Sin clasificar · " + limpio[:90]

def agrupar_registros(registros, reemplazos=None):
    grupos = defaultdict(list)
    reemplazos = reemplazos or {}
    for adf in registros:
        original = str(getattr(adf, "efecto", "") or "").strip()
        grupo = reemplazos.get(normalizar(original)) or sugerir(original)
        grupos[grupo].append((adf, original))
    return dict(sorted(grupos.items(), key=lambda par: (-len(par[1]), par[0])))
