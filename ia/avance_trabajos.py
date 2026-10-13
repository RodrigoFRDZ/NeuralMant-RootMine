"""Propuestas de actualización; nunca escribe datos ni supone una prueba aprobada."""
import json
from typing import Literal
from pydantic import BaseModel, Field
from ia.cliente import _generar

class PropuestaAvance(BaseModel):
    estado: Literal['Pendiente','En ejecución','Detenido','Terminado'] | None=None
    avance: int | None=Field(default=None,ge=0,le=100)
    pendiente: str | None=None
    hallazgos: str | None=None
    prueba: Literal['Pendiente','En prueba','Aprobada','Fallida','No requerida'] | None=None
    detalle_prueba: str | None=None
    etapas_completadas: list[int]=Field(default_factory=list)
    etapas_reabiertas: list[int]=Field(default_factory=list)

def proponer(mensaje,etapas=None):
    propuesta=_generar('Ordena la novedad de un supervisor para UN trabajo seleccionado. Solo usa el mensaje: no inventes porcentajes, estados, resultados ni pruebas. '
        'Un dato no mencionado se devuelve null. Trabajo terminado no significa prueba aprobada. Solo devuelve prueba Aprobada si se informa explícitamente una prueba exitosa. '
        'No requerida necesita una declaración explícita y motivo. Para detener un trabajo identifica el bloqueo. Para limpiar un pendiente usa cadena vacía solo si dice que está resuelto. '
        'Identifica por número las etapas explícitamente terminadas o reabiertas. Nunca presupongas etapas anteriores por haber terminado una posterior. Una etapa terminada no significa todo el trabajo terminado. No calcules porcentaje: el sistema lo suma con el plan. '
        'Hallazgos son hechos nuevos. No confundas ejecutor con supervisor. Toda propuesta será revisada y confirmada por el supervisor.',json.dumps({'mensaje':mensaje,'plan_etapas':etapas or []},ensure_ascii=False),PropuestaAvance)
    datos=propuesta.model_dump(exclude_none=True)
    for k in ('etapas_completadas','etapas_reabiertas'):
        if not datos[k]:datos.pop(k)
    return datos


def preparar_propuesta(trabajo,mensaje):
    from ia.etapas_trabajos import plan_base, porcentaje_escrito, calcular, proponer_plan
    escrito=porcentaje_escrito(mensaje)
    plan=trabajo.get('etapas') or plan_base(trabajo['descripcion'])
    nuevo=False
    if not plan and escrito is None:
        plan=proponer_plan(trabajo['descripcion']);nuevo=True
    datos=proponer(mensaje,plan)
    nuevas=datos.pop('etapas_completadas',[]);reabiertas=datos.pop('etapas_reabiertas',[])
    datos.pop('avance',None)
    if escrito is not None:
        datos.update(avance=escrito,origen_avance='informado_supervisor')
        if escrito==100:datos['estado']='Terminado'
        elif datos.get('estado')=='Terminado' or (escrito>0 and datos.get('estado')=='Pendiente'):datos['estado']='En ejecución'
    elif plan and (nuevas or reabiertas):
        valor,cerradas=calcular(plan,trabajo.get('etapas_confirmadas',[]),nuevas,reabiertas)
        datos.update(avance=valor,origen_avance='estimado_etapas',etapas_confirmadas=cerradas,etapas=plan)
        if valor==100:datos['estado']='Terminado'
        elif datos.get('estado')=='Terminado' or 'estado' not in datos:datos['estado']='En ejecución'
    if nuevo:datos.update(etapas=plan,plan_nuevo=True)
    return datos
