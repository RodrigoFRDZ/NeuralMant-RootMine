import os
from dataclasses import dataclass
from typing import TypeVar

import streamlit as st
from pydantic import BaseModel

from ia.esquemas import DiagnosticoInicial, InformeFinalIA, IshikawaIA, ProfundizacionCausal, RevisionEvidenciaPlan
from ia.prompts import CAUSAL_SISTEMA, DIAGNOSTICO_SISTEMA, INFORME_SISTEMA, ISHIKAWA_SISTEMA, EVIDENCIA_PLAN_SISTEMA

T = TypeVar("T", bound=BaseModel)


@dataclass
class ConfiguracionIA:
    proveedor: str
    api_key: str
    modelo: str


def _secret(nombre: str, valor_default: str = "") -> str:
    try:
        return str(st.secrets.get(nombre, valor_default))
    except Exception:
        return valor_default


def obtener_configuracion() -> ConfiguracionIA:
    # RootMine v4.0: una sola clave central para todos los usuarios.
    clave = _secret("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
    modelo = _secret("GEMINI_MODEL") or os.getenv("GEMINI_MODEL", "") or "gemini-3.1-flash-lite"
    return ConfiguracionIA(proveedor="Gemini", api_key=clave, modelo=modelo)


def _validar_clave(configuracion: ConfiguracionIA) -> None:
    if not configuracion.api_key:
        raise RuntimeError("No existe GEMINI_API_KEY central. Configúrala una sola vez en .streamlit/secrets.toml.")


def _gemini_estructurado(modelo: str, api_key: str, sistema: str, contenido: str, esquema: type[T]) -> T:
    try:
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise RuntimeError("Falta instalar google-genai. Ejecuta INSTALAR_ROOTMINE.bat.") from error

    client = genai.Client(api_key=api_key)
    respuesta = client.models.generate_content(
        model=modelo,
        contents=contenido,
        config=types.GenerateContentConfig(
            system_instruction=sistema,
            response_mime_type="application/json",
            response_schema=esquema,
            temperature=0.15,
            max_output_tokens=8192,
        ),
    )
    parsed = getattr(respuesta, "parsed", None)
    if parsed is not None:
        return parsed if isinstance(parsed, esquema) else esquema.model_validate(parsed)
    texto = (getattr(respuesta, "text", "") or "").strip()
    if not texto:
        raise RuntimeError("Gemini no devolvió contenido estructurado.")
    return esquema.model_validate_json(texto)


def _generar(sistema: str, contenido: str, esquema: type[T]) -> T:
    configuracion = obtener_configuracion()
    _validar_clave(configuracion)
    return _gemini_estructurado(configuracion.modelo, configuracion.api_key, sistema, contenido, esquema)


def generar_diagnostico(area: str, equipo: str, relato: str, aviso_sap: str = "", casos_similares: str = "") -> DiagnosticoInicial:
    contenido = f"Área: {area}\nEquipo: {equipo}\nAviso SAP: {aviso_sap or 'No informado'}\nRelato original:\n{relato}"
    if casos_similares:
        contenido += f"\n\nCasos históricos potencialmente similares:\n{casos_similares}\nÚsalos solo como referencia, no como evidencia."
    return _generar(DIAGNOSTICO_SISTEMA, contenido, DiagnosticoInicial)


def generar_ishikawa(area: str, equipo: str, relato: str, fenomeno: str, principio_funcionamiento: str, hechos: list[str]) -> IshikawaIA:
    contenido = (
        f"Área: {area}\nEquipo: {equipo}\nFenómeno validado: {fenomeno}\n"
        f"Principio de funcionamiento validado:\n{principio_funcionamiento}\n"
        f"Hechos confirmados:\n- " + "\n- ".join(hechos) + f"\nRelato original:\n{relato}"
    )
    return _generar(ISHIKAWA_SISTEMA, contenido, IshikawaIA)


def generar_cadenas_y_planes(efecto: str, principio_funcionamiento: str, causas_seleccionadas: list[str], contexto_validado: str) -> ProfundizacionCausal:
    contenido = (
        f"Fenómeno/efecto: {efecto}\nPrincipio de funcionamiento:\n{principio_funcionamiento}\n"
        f"Contexto validado:\n{contexto_validado}\nCausas seleccionadas para profundizar:\n- " + "\n- ".join(causas_seleccionadas)
    )
    return _generar(CAUSAL_SISTEMA, contenido, ProfundizacionCausal)


def generar_informe_final(contexto_completo: str) -> InformeFinalIA:
    return _generar(INFORME_SISTEMA, contexto_completo, InformeFinalIA)


def revisar_evidencia_plan(contexto: str, imagen=None, mime_type: str = "image/png", imagenes=None) -> RevisionEvidenciaPlan:
    """Revisa uno o varios respaldos visuales. `imagenes` acepta dicts con data/mime/label.
    Se mantiene `imagen` por compatibilidad con versiones previas.
    """
    configuracion = obtener_configuracion()
    _validar_clave(configuracion)
    respaldos = list(imagenes or [])
    if imagen and not respaldos:
        respaldos = [{"data": imagen, "mime": mime_type, "label": "Respaldo"}]
    if not respaldos:
        return _generar(EVIDENCIA_PLAN_SISTEMA, contexto, RevisionEvidenciaPlan)
    try:
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise RuntimeError("Falta instalar google-genai. Ejecuta INSTALAR_ROOTMINE.bat.") from error
    client = genai.Client(api_key=configuracion.api_key)
    contenido = [contexto]
    for idx, respaldo in enumerate(respaldos, start=1):
        data = respaldo.get("data") if isinstance(respaldo, dict) else None
        if not data:
            continue
        label = (respaldo.get("label") or f"Respaldo {idx}") if isinstance(respaldo, dict) else f"Respaldo {idx}"
        mime = (respaldo.get("mime") or "image/png") if isinstance(respaldo, dict) else "image/png"
        contenido.append(f"\n--- {label} ---")
        contenido.append(types.Part.from_bytes(data=data, mime_type=mime))
    respuesta = client.models.generate_content(
        model=configuracion.modelo,
        contents=contenido,
        config=types.GenerateContentConfig(
            system_instruction=EVIDENCIA_PLAN_SISTEMA,
            response_mime_type="application/json",
            response_schema=RevisionEvidenciaPlan,
            temperature=0.1,
            max_output_tokens=6144,
        ),
    )
    parsed = getattr(respuesta, "parsed", None)
    if parsed is not None:
        return parsed if isinstance(parsed, RevisionEvidenciaPlan) else RevisionEvidenciaPlan.model_validate(parsed)
    texto = (getattr(respuesta, "text", "") or "").strip()
    return RevisionEvidenciaPlan.model_validate_json(texto)

