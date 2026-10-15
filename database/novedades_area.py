"""Append-only area observations and explicit resolutions with actor/time trace."""
import json,hashlib
from contextlib import ExitStack
from datetime import datetime
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from database import trabajos as db
from motores.foco_partida import clasificar

def _fila(r):return dict(id=r.id,**json.loads(r.datos))
def _listar(s,n,area=None):
    q=select(db.NovedadArea).where(db.NovedadArea.programa==n).order_by(db.NovedadArea.id)
    if area is not None:q=q.where(db.NovedadArea.area==area)
    return [_fila(r) for r in s.scalars(q)]
def listar(correo,n,area=None):
    with Session(db.engine) as s:
        db._programa(s,db._usuario(s,correo),n)
        return _listar(s,n,area)

def guardar(correo,n,area,mensaje,clave,categoria='Automática',impacto='Por evaluar',capturado='',resuelve=None,_sesion=None):
    clave=str(UUID(str(clave)));area=str(area).strip();mensaje=str(mensaje).strip()
    if not mensaje or len(mensaje)>10000:raise ValueError('Escribe una novedad de hasta 10.000 caracteres.')
    if capturado:
        momento=datetime.fromisoformat(capturado.replace('Z','+00:00'))
        if momento.tzinfo is None:raise ValueError('La hora de captura debe incluir zona horaria.')
    firma=hashlib.sha256(json.dumps([area,mensaje,categoria,impacto,capturado,resuelve],ensure_ascii=False).encode()).hexdigest()
    with ExitStack() as stack:
        if _sesion is None:s=stack.enter_context(Session(db.engine));stack.enter_context(s.begin())
        else:s=_sesion
        u=db._usuario(s,correo);db._programa(s,u,n,True)
        if not db.puede_chat(u):raise ValueError('Solo supervisores, coordinadores o administración pueden registrar novedades.')
        previo=s.scalar(select(db.NovedadArea).where(db.NovedadArea.clave==clave))
        if previo:
            d=json.loads(previo.datos)
            if previo.programa!=n or d['usuario']!=u['correo'] or previo.firma!=firma:raise ValueError('La clave corresponde a otra novedad.')
            return previo.id
        db._editable(s,n)
        areas={json.loads(t)['area'] for t in s.scalars(select(db.TrabajoFinSemana.datos).where(db.TrabajoFinSemana.programa==n))}
        if area not in areas:raise ValueError('Elige un área de esta programación.')
        clasificacion=clasificar(mensaje,categoria,impacto);original=None
        if resuelve is not None:
            original=s.get(db.NovedadArea,int(resuelve),with_for_update=True)
            if not original or original.programa!=n or original.area!=area:raise ValueError('Hallazgo no disponible en esta área.')
            dato=json.loads(original.datos)
            if dato.get('estado')!='Abierto' or dato.get('resuelve'):raise ValueError('Este hallazgo ya se resolvió.')
            clasificacion.update(categoria='Seguimiento',impacto=dato['impacto'],clasificacion='Resolución informada por supervisor')
        ahora=datetime.utcnow().isoformat()
        datos=dict(area=area,mensaje=mensaje,fecha=ahora,capturado=capturado or ahora+'Z',usuario=u['correo'],nombre=u['nombre'],rol=u.get('rol',''),estado='Resuelto' if original else 'Abierto',resuelve=int(resuelve) if original else None,**clasificacion)
        r=db.NovedadArea(programa=n,clave=clave,firma=firma,area=area,datos=json.dumps(datos,ensure_ascii=False));s.add(r);s.flush()
        if original:
            dato.update(estado='Resuelto',cierre=dict(registro=r.id,fecha=ahora,nombre=u['nombre'],usuario=u['correo'],mensaje=mensaje))
            original.datos=json.dumps(dato,ensure_ascii=False)
        return r.id
