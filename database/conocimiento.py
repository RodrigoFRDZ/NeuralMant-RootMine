import json
import re
from dataclasses import dataclass

from database.repositorio_adf import listar_adf


@dataclass
class CasoSimilar:
    id: int
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
    equipo: str,
    relato: str,
    limite: int = 3,
) -> list[CasoSimilar]:
    consulta = _tokens(f"{equipo} {relato}")
    if not consulta:
        return []

    resultados: list[CasoSimilar] = []
    for adf in listar_adf():
        texto = " ".join([
            adf.equipo or "",
            adf.relato_original or "",
            adf.efecto or "",
            adf.conclusion or "",
            adf.causas_priorizadas or "",
        ])
        caso = _tokens(texto)
        if not caso:
            continue

        interseccion = len(consulta & caso)
        similitud = interseccion / max(len(consulta), 1)
        mismo_equipo = equipo.strip().lower() in (adf.equipo or "").lower()
        if mismo_equipo:
            similitud += 0.30

        if similitud >= 0.18:
            resultados.append(CasoSimilar(
                id=adf.id,
                equipo=adf.equipo,
                efecto=adf.efecto,
                conclusion=adf.conclusion,
                similitud=min(similitud, 1.0),
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
            f"ADF #{caso.id} | Equipo: {caso.equipo} | "
            f"Efecto: {caso.efecto or 'No registrado'} | "
            f"Conclusión: {caso.conclusion or 'No registrada'}"
        )
    return "\n".join(bloques)
