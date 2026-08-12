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
    consulta = _tokens(f"{centro} {numero_equipo} {equipo} {relato}")
    if not consulta:
        return []

    resultados: list[CasoSimilar] = []
    for adf in listar_adf():
        texto = " ".join([
            getattr(adf, "centro", "") or "",
            getattr(adf, "planta", "") or "",
            getattr(adf, "numero_equipo", "") or "",
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
        mismo_numero = bool(numero_equipo.strip()) and numero_equipo.strip().lower() == (getattr(adf, "numero_equipo", "") or "").strip().lower()
        misma_descripcion = equipo.strip().lower() in (adf.equipo or "").lower()
        mismo_centro = bool(centro.strip()) and centro.strip().lower() == (getattr(adf, "centro", "") or "").strip().lower()
        if mismo_numero:
            similitud += 0.55
        elif misma_descripcion:
            similitud += 0.30
        # El centro ayuda a priorizar contexto local sin excluir conocimiento de otras plantas.
        if mismo_centro:
            similitud += 0.08

        if similitud >= 0.18:
            resultados.append(CasoSimilar(
                id=adf.id,
                centro=getattr(adf, "centro", "") or "No registrado",
                numero_equipo=getattr(adf, "numero_equipo", "") or "No registrado",
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
            f"ADF #{caso.id} | Centro: {caso.centro} | Equipo: {caso.equipo} | "
            f"Identificador N°: {caso.numero_equipo} | Efecto: {caso.efecto or 'No registrado'} | "
            f"Conclusión: {caso.conclusion or 'No registrada'}"
        )
    return "\n".join(bloques)
