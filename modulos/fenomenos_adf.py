"""Normalización conservadora de fenómenos ADF: modo + componente específico.

No utiliza textos SAP como título y no inventa componentes cuando faltan.
"""
import re
import unicodedata

COMPONENTES = (
    ("sello mecánico", ("sello mecanico", "sello mecánico")),
    ("rodamiento", ("rodamiento", "rodamientos", "cojinete", "ruleman", "rulemán")),
    ("rotor", ("rotor", "rotores", "álabes del rotor", "alabes del rotor")),
    ("álabe", ("álabe", "alabe", "aspas")),
    ("eje", ("eje", "ejes")),
    ("cadena", ("cadena", "cadenas")),
    ("correa", ("correa", "correas")),
    ("engranaje", ("engranaje", "engranajes")),
    ("acoplamiento", ("acoplamiento", "acople")),
    ("sensor", ("sensor", "sensores", "transductor")),
    ("válvula", ("válvula", "valvula", "valvulas", "válvulas")),
    ("bomba", ("bomba", "bombas")),
    ("motor", ("motor", "motores")),
    ("cilindro", ("cilindro", "cilindros")),
    ("manguera", ("manguera", "mangueras")),
    ("tubería", ("tubería", "tuberia", "cañeria", "cañería")),
    ("cuchilla", ("cuchilla", "cuchillas")),
    ("mordaza", ("mordaza", "mordazas")),
    ("conector", ("conector", "conectores")),
)
MODOS = (
    ("Rotura", ("rotura", "fractura", "quiebre", "quebrado", "partido", "roto", "corte", "cortada")),
    ("Fuga", ("fuga", "filtración", "filtracion", "pérdida de fluido", "perdida de fluido")),
    ("Sobrecalentamiento", ("sobrecalentamiento", "temperatura elevada", "alta temperatura", "recalentamiento")),
    ("Desgaste", ("desgaste", "erosión", "erosion", "abrasión", "abrasion")),
    ("Deformación", ("deformación", "deformacion", "doblado", "torcido")),
    ("Obstrucción", ("obstrucción", "obstruccion", "atasco", "bloqueo")),
    ("Pérdida de señal", ("sin señal", "sin senal", "pérdida de señal", "perdida de senal")),
    ("Vibración excesiva", ("vibración", "vibracion", "vibraciones")),
    ("Cavitación", ("cavitación", "cavitacion")),
    ("Aflojamiento", ("aflojamiento", "suelto", "holgura")),
)

def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "").lower())
    return "".join(c for c in texto if not unicodedata.combining(c))

def _coincidencias(texto, diccionario):
    t = _normalizar(texto)
    hallazgos = []
    for etiqueta, alias in diccionario:
        for variante in alias:
            v = _normalizar(variante)
            m = re.search(r"(?<!\\w)" + re.escape(v) + r"(?!\\w)", t)
            if m:
                hallazgos.append((etiqueta, m.start(), len(v)))
    return hallazgos

def fenomeno_adf(adf):
    """(etiqueta, confiable): sin fenómeno explícito no inventar etiqueta."""
    efecto = str(getattr(adf, "efecto", "") or "").strip()
    conclusion = str(getattr(adf, "conclusion", "") or "").strip()
    # Priorizar el relato del fenómeno; usar conclusión como apoyo.
    for texto in (efecto, conclusion):
        componentes = _coincidencias(texto, COMPONENTES)
        modos = _coincidencias(texto, MODOS)
        if not componentes or not modos:
            continue
        # Elegir pareja semánticamente más cercana, evitando emparejar
        # componentes lejanos cuando el texto describe varias fallas.
        pares = sorted(
            ((abs(c[1]-m[1]), -c[2], c[1], c[0], m[0])
             for c in componentes for m in modos),
            key=lambda x: x[:3]
        )
        distancia, _, _, componente, modo = pares[0]
        if distancia > 115:
            continue
        enlace = "por " if modo == "Fuga" and componente == "sello mecánico" else "de "
        return f"{modo} {enlace}{componente}", True
    return "Fenómeno por identificar", False
