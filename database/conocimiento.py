import json
import re
from dataclasses import dataclass

from database.repositorio_adf import listar_adf


@dataclass
class CasoSimilar:
    id: int
    centro: str
    numero_equipo: str
    equipo: str
    efecto: str
    conclusion: str
    similitud: float


PALABRAS_VACIAS = {
    "para", "como", "este", "esta", "esto", "desde", "hasta", "porque",
    "equipo", "falla", "fallo", "realiza", "realizó", "cambio", "normal",
    "funcionamiento", "sistema", "alarma", "presenta", "encuentra", "se",
    "el", "la", "los", "las", "un", "una", "de", "del", "y", "o", "en",
    "por", "con", "al", "que", "no", "su", "a",
}


def _tokens(texto: str) -> set[str]:
    palabras = re.findall(r"[a-záéíóúñ0-9]{3,}", texto.lower())
    return {p for p in palabras if p not in PALABRAS_VACIAS}


def buscar_casos_similares(
    centro: str,
    numero_equipo: str,
    equipo: str,
    relato: str,
    limite: int = 5,
) -> list[CasoSimilar]:
    # La similitud se evalúa SOLO dentro del mismo activo.
    # Si existe N° de equipo, ese identificador manda. Si no existe, se exige
    # coincidencia exacta de la descripción normalizada del equipo.
    numero_consulta = (numero_equipo or "").strip().lower()
    equipo_consulta = " ".join((equipo or "").strip().lower().split())
    consulta_falla = _tokens(relato or "")

    resultados: list[CasoSimilar] = []
    for adf in listar_adf():
        # Los borradores se controlan por separado; no deben presentarse como conocimiento histórico.
        if (getattr(adf, "estado", "") or "") == "Borrador":
            continue

        numero_adf = (getattr(adf, "numero_equipo", "") or "").strip().lower()
        equipo_adf = " ".join((adf.equipo or "").strip().lower().split())

        if numero_consulta:
            mismo_activo = numero_consulta == numero_adf
        else:
            mismo_activo = bool(equipo_consulta) and equipo_consulta == equipo_adf

        if not mismo_activo:
            continue

        texto_falla = " ".join([
            adf.relato_original or "",
            adf.efecto or "",
            adf.conclusion or "",
            adf.causas_priorizadas or "",
        ])
        caso_falla = _tokens(texto_falla)

        # Si no hay suficiente texto, igual se puede mostrar el historial del mismo equipo,
        # pero con una similitud baja. Las palabras genéricas de otros equipos nunca entran.
        if consulta_falla and caso_falla:
            interseccion = len(consulta_falla & caso_falla)
            union = len(consulta_falla | caso_falla)
            similitud_falla = interseccion / max(union, 1)
        else:
            similitud_falla = 0.0

        resultados.append(CasoSimilar(
            id=adf.id,
            centro=getattr(adf, "centro", "") or "No registrado",
            numero_equipo=getattr(adf, "numero_equipo", "") or "No registrado",
            equipo=adf.equipo,
            efecto=adf.efecto,
            conclusion=adf.conclusion,
            # 50% base por ser el mismo activo + similitud real de la falla.
            similitud=min(0.50 + (similitud_falla * 0.50), 1.0),
        ))

    return sorted(
        resultados,
        key=lambda caso: caso.similitud,
        reverse=True,
    )[:limite]


def formatear_contexto_casos(casos: list[CasoSimilar]) -> str:
    bloques = []
    for caso in casos:
        bloques.append(
            f"ADF #{caso.id} | Centro: {caso.centro} | Equipo: {caso.equipo} | "
            f"Identificador N°: {caso.numero_equipo} | Efecto: {caso.efecto or 'No registrado'} | "
            f"Conclusión: {caso.conclusion or 'No registrada'}"
        )
    return "\n".join(bloques)
