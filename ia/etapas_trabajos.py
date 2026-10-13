"""Planes orientativos y cálculo trazable; nunca presupone etapas anteriores."""
import re
import math
from pydantic import BaseModel, Field
from ia.cliente import _generar

ACEITE=[{'etapa':'Preparación y aislamiento del equipo','peso':15},
        {'etapa':'Drenaje del aceite usado','peso':25},
        {'etapa':'Carga del aceite nuevo','peso':35},
        {'etapa':'Revisión de nivel y fugas','peso':15},
        {'etapa':'Prueba y entrega del equipo','peso':10}]

def validar_plan(plan):
    if not isinstance(plan,list) or not 2<=len(plan)<=10:raise ValueError('Define entre 2 y 10 etapas.')
    salida=[]
    for fila in plan:
        nombre=str(fila.get('etapa','')).strip();peso=fila.get('peso')
        if not nombre or isinstance(peso,bool) or not isinstance(peso,(int,float)) or not math.isfinite(peso) or int(peso)!=peso or not 1<=peso<=100:raise ValueError('Cada etapa necesita nombre y peso entero positivo.')
        salida.append(dict(etapa=nombre,peso=int(peso)))
    if sum(x['peso'] for x in salida)!=100:raise ValueError('Los pesos deben sumar 100 %.')
    if len({x['etapa'].lower() for x in salida})!=len(salida):raise ValueError('Evita etapas duplicadas.')
    return salida

def plan_base(descripcion):
    if re.search(r'camb(?:io)?\s+(?:de\s+)?aceite',descripcion,re.I):return [dict(x) for x in ACEITE]
    return []

class Etapa(BaseModel):
    etapa:str
    peso:int=Field(ge=1,le=100)
class Plan(BaseModel):
    etapas:list[Etapa]

def proponer_plan(descripcion):
    base=plan_base(descripcion)
    if base:return base
    res=_generar('Propón de 2 a 10 etapas generales para estimar el avance del trabajo descrito. No des procedimientos operativos, valores técnicos ni instrucciones de seguridad. '
        'Nombres cortos, pesos enteros positivos que sumen 100. Es un plan orientativo para revisar, no evidencia de ejecución. No supongas que las etapas ya ocurrieron.',descripcion,Plan)
    return validar_plan([e.model_dump() for e in res.etapas])

def porcentaje_escrito(mensaje):
    valores=re.findall(r'(?<![\d.])(\d{1,3}(?:[.,]\d+)?)\s*%',mensaje)
    if not valores:
        valores=re.findall(r'(?:avance|vamos\s+al|va\s+al|progreso)\s*(?:de|:|al)?\s*(\d{1,3})(?!\d)',mensaje,re.I)
    if len(valores)!=1:return None
    v=float(valores[0].replace(',','.'))
    return int(v+0.5) if 0<=v<=100 else None

def calcular(plan,anteriores,completadas,reabiertas):
    plan=validar_plan(plan);validos=set(range(1,len(plan)+1))
    valores=[*anteriores,*completadas,*reabiertas]
    if any(isinstance(i,bool) or not isinstance(i,int) or i not in validos for i in valores):raise ValueError('La propuesta incluye una etapa no definida.')
    cerradas=(set(anteriores)|set(completadas))-set(reabiertas)
    return sum(plan[i-1]['peso'] for i in cerradas),sorted(cerradas)
