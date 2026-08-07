import os
from dataclasses import dataclass
from typing import TypeVar

import streamlit as st
from openai import OpenAI
from pydantic import BaseModel

from ia.esquemas import (
    DiagnosticoInicial,
    InformeFinalIA,
    IshikawaIA,
    ProfundizacionCausal,
)
from ia.prompts import (
    CAUSAL_SISTEMA,
    DIAGNOSTICO_SISTEMA,
    INFORME_SISTEMA,
    ISHIKAWA_SISTEMA,
)

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
    proveedor = st.session_state.get("proveedor_ia", "Gemini").strip() or "Gemini"
    if proveedor == "OpenAI":
        clave = (
            st.session_state.get("api_key_temporal", "").strip()
            or _secret("OPENAI_API_KEY")
            or os.getenv("OPENAI_API_KEY", "")
        )
        modelo = (
            st.session_state.get("modelo_ia", "").strip()
            or _secret("OPENAI_MODEL")
            or os.getenv("OPENAI_MODEL", "")
            or "gpt-5.6"
        )
    else:
        clave = (
            st.session_state.get("api_key_temporal", "").strip()
            or _secret("GEMINI_API_KEY")
            or os.getenv("GEMINI_API_KEY", "")
            or os.getenv("GOOGLE_API_KEY", "")
        )
        modelo = (
            st.session_state.get("modelo_ia", "").strip()
            or _secret("GEMINI_MODEL")
            or os.getenv("GEMINI_MODEL", "")
            or "gemini-3.1-flash-lite"
        )
    return ConfiguracionIA(proveedor=proveedor, api_key=clave, modelo=modelo)


def _validar_clave(configuracion: ConfiguracionIA) -> None:
    if configuracion.api_key:
        return
    variable = "GEMINI_API_KEY" if configuracion.proveedor == "Gemini" else "OPENAI_API_KEY"
    raise RuntimeError(
        f"No existe una clave para {configuracion.proveedor}. "
        f"Configura {variable} en .streamlit/secrets.toml."
    )


def _gemini_estructurado(
    modelo: str, api_key: str, sistema: str, contenido: str, esquema: type[T]
) -> T:
    try:
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise RuntimeError(
            "Falta instalar google-genai. Ejecuta: pip install -r requirements.txt"
        ) from error

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


def _openai_estructurado(
    modelo: str, api_key: str, sistema: str, contenido: str, esquema: type[T]
) -> T:
    client = OpenAI(api_key=api_key)
    respuesta = client.responses.parse(
        model=modelo,
        input=[
            {"role": "system", "content": sistema},
            {"role": "user", "content": contenido},
        ],
        text_format=esquema,
    )
    if respuesta.output_parsed is None:
        raise RuntimeError("OpenAI no devolvió contenido estructurado.")
    return respuesta.output_parsed


def _generar(sistema: str, contenido: str, esquema: type[T]) -> T:
    configuracion = obtener_configuracion()
    _validar_clave(configuracion)
    if configuracion.proveedor == "Gemini":
        return _gemini_estructurado(
            configuracion.modelo,
            configuracion.api_key,
            sistema,
            contenido,
            esquema,
        )
    return _openai_estructurado(
        configuracion.modelo,
        configuracion.api_key,
        sistema,
        contenido,
        esquema,
    )


def generar_diagnostico(
    area: str,
    equipo: str,
    relato: str,
    aviso_sap: str = "",
    casos_similares: str = "",
) -> DiagnosticoInicial:
    contenido = (
        f"Área: {area}\nEquipo: {equipo}\n"
        f"Aviso SAP: {aviso_sap or 'No informado'}\n"
        f"Relato original:\n{relato}"
    )
    if casos_similares:
        contenido += (
            "\n\nCasos históricos potencialmente similares:\n"
            f"{casos_similares}\n"
            "Úsalos solo como referencia, no como evidencia."
        )
    return _generar(DIAGNOSTICO_SISTEMA, contenido, DiagnosticoInicial)


def generar_ishikawa(
    area: str,
    equipo: str,
    relato: str,
    fenomeno: str,
    principio_funcionamiento: str,
    hechos: list[str],
) -> IshikawaIA:
    contenido = (
        f"Área: {area}\nEquipo: {equipo}\n"
        f"Fenómeno validado: {fenomeno}\n"
        f"Principio de funcionamiento validado:\n{principio_funcionamiento}\n"
        f"Hechos confirmados:\n- " + "\n- ".join(hechos) +
        f"\nRelato original:\n{relato}"
    )
    return _generar(ISHIKAWA_SISTEMA, contenido, IshikawaIA)


def generar_cadenas_y_planes(
    efecto: str,
    principio_funcionamiento: str,
    causas_seleccionadas: list[str],
    contexto_validado: str,
) -> ProfundizacionCausal:
    contenido = (
        f"Fenómeno/efecto: {efecto}\n"
        f"Principio de funcionamiento:\n{principio_funcionamiento}\n"
        f"Contexto validado:\n{contexto_validado}\n"
        "Causas seleccionadas para profundizar:\n- "
        + "\n- ".join(causas_seleccionadas)
    )
    return _generar(CAUSAL_SISTEMA, contenido, ProfundizacionCausal)


def generar_informe_final(contexto_completo: str) -> InformeFinalIA:
    return _generar(INFORME_SISTEMA, contexto_completo, InformeFinalIA)
