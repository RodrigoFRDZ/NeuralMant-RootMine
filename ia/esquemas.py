from typing import Literal

from pydantic import BaseModel, Field


class DiagnosticoInicial(BaseModel):
    hechos_confirmados: list[str] = Field(default_factory=list)
    sintomas: list[str] = Field(default_factory=list)
    componentes: list[str] = Field(default_factory=list)
    condicion_encontrada: str
    accion_recuperacion: str
    informacion_faltante: list[str] = Field(default_factory=list)
    fenomeno_propuesto: str
    justificacion_fenomeno: str
    principio_funcionamiento: str
    preguntas_iniciales: list[str] = Field(default_factory=list)


class HipotesisCausa(BaseModel):
    causa: str
    mecanismo: str
    prioridad_revision: Literal["Alta", "Media", "Baja"]
    preguntas_validacion: list[str] = Field(default_factory=list)


class IshikawaIA(BaseModel):
    maquina: list[HipotesisCausa] = Field(default_factory=list)
    metodo: list[HipotesisCausa] = Field(default_factory=list)
    mano_obra: list[HipotesisCausa] = Field(default_factory=list)
    material: list[HipotesisCausa] = Field(default_factory=list)
    medicion: list[HipotesisCausa] = Field(default_factory=list)
    medio_ambiente: list[HipotesisCausa] = Field(default_factory=list)
    resumen_tecnico: str
    advertencias: list[str] = Field(default_factory=list)


class NivelCausalSugerido(BaseModel):
    nivel: int
    pregunta: str
    respuesta_sugerida: str
    justificacion_tecnica: str
    evidencia_requerida: str


class CadenaCausalSugerida(BaseModel):
    causa: str
    niveles: list[NivelCausalSugerido] = Field(default_factory=list, min_length=3, max_length=5)
    causa_raiz_preliminar: str
    advertencia: str = "Debe validarse en terreno antes de declararse causa raíz."


class AccionPrevencion(BaseModel):
    accion: str
    objetivo: str
    relacion_con_causa: str
    responsable_sugerido: str = "Por definir"
    plazo_sugerido: str = "Por definir"
    evidencia_de_implementacion: str


class ProfundizacionCausal(BaseModel):
    cadenas: list[CadenaCausalSugerida] = Field(default_factory=list)
    plan_prevencion: list[AccionPrevencion] = Field(default_factory=list)
    observaciones_generales: list[str] = Field(default_factory=list)


class InformeFinalIA(BaseModel):
    titulo: str
    resumen_ejecutivo: str
    descripcion_evento: str
    principio_funcionamiento: str
    fenomeno_investigado: str
    sintesis_ishikawa: str
    conclusion_tecnica: str
    leccion_aprendida: str
    recomendaciones_cierre: list[str] = Field(default_factory=list)
    pendientes_validacion: list[str] = Field(default_factory=list)
