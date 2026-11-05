import os
import re
import time
import random
import json
import logging
import urllib.request
import urllib.error
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TypeVar

import streamlit as st
from pydantic import BaseModel

from ia.esquemas import DiagnosticoInicial, InformeFinalIA, IshikawaIA, ProfundizacionCausal, RevisionEvidenciaPlan
from ia.prompts import CAUSAL_SISTEMA, DIAGNOSTICO_SISTEMA, INFORME_SISTEMA, ISHIKAWA_SISTEMA, EVIDENCIA_PLAN_SISTEMA
from database.metricas_sistema import registrar_uso_ia

configuracion_ia_contexto = ContextVar("configuracion_ia_contexto", default=None)
usuario_ia_contexto = ContextVar("usuario_ia_contexto", default="")

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




class GearBotTemporalmenteNoDisponible(RuntimeError):
    """Error amigable cuando Gemini rechaza temporalmente por cuota/rate limit."""


def _usuario_email_actual() -> str:
    if usuario_ia_contexto.get():return usuario_ia_contexto.get()
    try:
        usuario = st.session_state.get("usuario_actual") or {}
        return (usuario.get("correo") or "").strip().lower()
    except Exception:
        return ""


def _es_error_cuota(error: Exception) -> bool:
    texto = str(error).lower()
    indicadores = (
        "429", "resource_exhausted", "resource exhausted", "quota",
        "rate limit", "too many requests", "exceeded your current quota",
    )
    return any(x in texto for x in indicadores)


def _mensaje_cuota(error: Exception) -> str:
    texto = str(error)
    espera = None
    patrones = [
        r"retry\s+in\s+([0-9.]+)s",
        r"retrydelay['\"=: ]+([0-9.]+)s",
        r"retry after\s+([0-9.]+)",
    ]
    for patron in patrones:
        m = re.search(patron, texto, flags=re.IGNORECASE)
        if m:
            try:
                espera = max(1, int(float(m.group(1))))
                break
            except Exception:
                pass

    base = (
        "🔧 GearBot está experimentando algunos inconvenientes técnicos. "
        "Puedes continuar trabajando en RootMine e intentarlo nuevamente en unos instantes."
    )
    if espera:
        if espera < 60:
            base += f" Intenta nuevamente en aproximadamente {espera} segundos."
        else:
            base += f" Intenta nuevamente en aproximadamente {max(1, round(espera / 60))} minutos."
    return base


def mensaje_amigable_ia(error: Exception) -> str | None:
    if isinstance(error, GearBotTemporalmenteNoDisponible):
        return str(error)
    if _es_error_cuota(error):
        return _mensaje_cuota(error)
    return None


def limites_configurados() -> dict:
    def _entero(nombre: str) -> int:
        try:
            valor = _secret(nombre, "0")
            return max(0, int(float(valor or 0)))
        except Exception:
            return 0

    return {
        "hora": _entero("GEMINI_HOURLY_LIMIT"),
        "dia": _entero("GEMINI_DAILY_LIMIT"),
    }


def _openai_respaldo(sistema: str, contenido: str, esquema: type[T]) -> T:
    """Respaldo independiente optativo; solo se activa con OPENAI_API_KEY."""
    clave = _secret("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    if not clave:
        raise RuntimeError("Respaldo independiente no configurado")
    modelo = _secret("OPENAI_FALLBACK_MODEL") or os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4.1-mini")
    payload = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": sistema + "\nDevuelve exclusivamente un objeto JSON válido que cumpla este esquema: " + json.dumps(esquema.model_json_schema(), ensure_ascii=False)},
            {"role": "user", "content": contenido},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.15,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + clave, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=65) as respuesta:
        data = json.load(respuesta)
    texto = data["choices"][0]["message"]["content"]
    return esquema.model_validate_json(texto)


def _gemini_estructurado(modelo: str, api_key: str, sistema: str, contenido: str, esquema: type[T]) -> T:
    try:
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise RuntimeError("Falta instalar google-genai. Ejecuta INSTALAR_ROOTMINE.bat.") from error

    rapido = getattr(esquema, "__name__", "") == "NovedadAutomatica"
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=25000 if rapido else 60000))
    operacion = getattr(esquema, "__name__", "GeneracionIA")
    respaldo = _secret("GEMINI_FALLBACK_MODEL") or os.getenv("GEMINI_FALLBACK_MODEL", "")
    # Modelo secundario independiente de configuración manual; se puede cambiar en Secrets.
    modelos = list(dict.fromkeys([modelo, respaldo.strip() or "gemini-2.5-flash"]))
    ultimo_error = None
    for modelo_actual in modelos:
        for intento in range(2):
            try:
                respuesta = client.models.generate_content(
                    model=modelo_actual,
                    contents=contenido,
                    config=types.GenerateContentConfig(
                        system_instruction=sistema,
                        response_mime_type="application/json",
                        response_schema=esquema,
                        temperature=0.15,
                        max_output_tokens=2048 if rapido else 8192,
                    ),
                )
                parsed = getattr(respuesta, "parsed", None)
                if parsed is not None:
                    resultado = parsed if isinstance(parsed, esquema) else esquema.model_validate(parsed)
                else:
                    texto = (getattr(respuesta, "text", "") or "").strip()
                    resultado = esquema.model_validate_json(texto)
                registrar_uso_ia(modelo_actual, operacion, "ok", _usuario_email_actual())
                return resultado
            except Exception as error:
                ultimo_error = error
                texto_error = str(error).lower()
                temporal = any(x in texto_error for x in (
                    "503", "502", "504", "unavailable", "high demand", "overloaded",
                    "429", "resource_exhausted", "rate limit", "timeout", "timed out",
                ))
                registrar_uso_ia(modelo_actual, operacion, "temporal" if temporal else "error", _usuario_email_actual())
                logging.getLogger(__name__).warning("GearBot IA: modelo=%s intento=%s error=%s", modelo_actual, intento + 1, type(error).__name__)
                if not temporal:
                    # Error de permisos/configuración: otro modelo puede funcionar, pero no repetir el mismo.
                    break
                if intento == 0:
                    time.sleep(2 + random.uniform(0, 0.5))

    if _secret("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"):
        try:
            resultado = _openai_respaldo(sistema, contenido, esquema)
            registrar_uso_ia("respaldo_externo", operacion, "ok", _usuario_email_actual())
            return resultado
        except Exception as error:
            logging.getLogger(__name__).warning("GearBot IA: respaldo externo falló: %s", type(error).__name__)
            registrar_uso_ia("respaldo_externo", operacion, "error", _usuario_email_actual())

    raise GearBotTemporalmenteNoDisponible(
        "🔧 GearBot está experimentando algunos inconvenientes técnicos en este momento. "
        "Tu análisis y los avances realizados permanecen guardados. "
        "Intenta nuevamente en unos instantes."
    ) from None


def _generar(sistema: str, contenido: str, esquema: type[T]) -> T:
    configuracion = configuracion_ia_contexto.get() or obtener_configuracion()
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
    try:
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
        registrar_uso_ia(configuracion.modelo, "RevisionEvidenciaPlan", "ok", _usuario_email_actual())
    except Exception as error:
        if _es_error_cuota(error):
            registrar_uso_ia(configuracion.modelo, "RevisionEvidenciaPlan", "cuota", _usuario_email_actual())
            raise GearBotTemporalmenteNoDisponible(_mensaje_cuota(error)) from None
        registrar_uso_ia(configuracion.modelo, "RevisionEvidenciaPlan", "error", _usuario_email_actual())
        raise
    parsed = getattr(respuesta, "parsed", None)
    if parsed is not None:
        return parsed if isinstance(parsed, RevisionEvidenciaPlan) else RevisionEvidenciaPlan.model_validate(parsed)
    texto = (getattr(respuesta, "text", "") or "").strip()
    return RevisionEvidenciaPlan.model_validate_json(texto)

