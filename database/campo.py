"""Scoped device sessions and atomic/idempotent synchronization."""
import base64
import hashlib
import json
import secrets
from datetime import datetime,timedelta
from uuid import UUID
from sqlalchemy import String,Integer,DateTime,Boolean,ForeignKey,UniqueConstraint,select,delete
from sqlalchemy.orm import Mapped,mapped_column,Session
from database.modelos import Base
from database import trabajos as db
from motores.pruebas_trabajos import transicion,desde_mensaje
from ia.novedad_automatica import directo,combinar

class AccesoCampo(Base):
    __tablename__='acceso_campo'
    clave: Mapped[str]=mapped_column(String(64),primary_key=True)
    usuario: Mapped[str]=mapped_column(String(180))
    programa: Mapped[int]=mapped_column(ForeignKey('programa_fin_semana.id'),index=True)
    tipo: Mapped[str]=mapped_column(String(15))
    vence: Mapped[datetime]=mapped_column(DateTime)
    usado: Mapped[bool]=mapped_column(Boolean,default=False)

class ReciboCampo(Base):
    __tablename__='recibo_campo'
    id: Mapped[int]=mapped_column(primary_key=True)
    usuario: Mapped[str]=mapped_column(String(180))
    uuid: Mapped[str]=mapped_column(String(36))
    programa: Mapped[int]=mapped_column(ForeignKey('programa_fin_semana.id'),index=True)
    trabajo: Mapped[int]=mapped_column(Integer)
    firma: Mapped[str]=mapped_column(String(64))
    version: Mapped[int]=mapped_column(Integer)
    fecha: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(UniqueConstraint('usuario','uuid'),)

class AccesoInvalido(ValueError):pass

def _hash(valor):return hashlib.sha256(valor.encode()).hexdigest()

def emitir_ticket(correo,n):
    valor=secrets.token_urlsafe(32)
    with Session(db.engine) as s,s.begin():
        u=db._usuario(s,correo);db._programa(s,u,n)
        s.execute(delete(AccesoCampo).where(AccesoCampo.vence<datetime.utcnow()))
        s.add(AccesoCampo(clave=_hash(valor),usuario=correo,programa=n,tipo='ticket',vence=datetime.utcnow()+timedelta(minutes=5)))
    return valor

def activar(ticket):
    valor=secrets.token_urlsafe(32)
    with Session(db.engine) as s,s.begin():
        acceso=s.get(AccesoCampo,_hash(ticket),with_for_update=True)
        if not acceso or acceso.tipo!='ticket' or acceso.usado or acceso.vence<=datetime.utcnow():raise AccesoInvalido('El enlace venció. Abre Vista de terreno nuevamente desde NeuralMant.')
        u=db._usuario(s,acceso.usuario);db._programa(s,u,acceso.programa)
        acceso.usado=True
        s.add(AccesoCampo(clave=_hash(valor),usuario=acceso.usuario,programa=acceso.programa,tipo='sesion',vence=datetime.utcnow()+timedelta(days=7)))
    return valor

def _autorizar(s,token):
    acceso=s.get(AccesoCampo,_hash(token))
    if not acceso or acceso.tipo!='sesion' or acceso.usado or acceso.vence<=datetime.utcnow():raise AccesoInvalido('Renueva el acceso desde NeuralMant. Las novedades locales se conservan.')
    try:
        u=db._usuario(s,acceso.usuario);p=db._programa(s,u,acceso.programa)
    except ValueError as exc:raise AccesoInvalido(str(exc)) from exc
    return u,p

def cerrar(token):
    with Session(db.engine) as s,s.begin():
        acceso=s.get(AccesoCampo,_hash(token))
        if acceso:acceso.usado=True

def snapshot(token):
    with Session(db.engine) as s:
        u,p=_autorizar(s,token);archivo=s.get(db.HistoricoTrabajo,p.id)
        filas=[db._fila(t) for t in s.scalars(select(db.TrabajoFinSemana).where(db.TrabajoFinSemana.programa==p.id).order_by(db.TrabajoFinSemana.id))]
        for d in filas:
            ultima=s.scalar(select(db.NovedadIA).where(db.NovedadIA.trabajo==d['id']).order_by(db.NovedadIA.id.desc()))
            if ultima:d['ia']=dict(estado=ultima.estado,detalle=ultima.detalle)
        return dict(usuario={'correo':u['correo'],'nombre':u['nombre'],'puede_editar':db.puede_chat(u)},programa={'id':p.id,'titulo':p.titulo,'centro':p.centro,'inicio':p.inicio,'fin':p.fin,'cerrado':bool(archivo)},trabajos=filas,actualizado=datetime.utcnow().isoformat()+'Z')

def sincronizar(token,evento):
    if not isinstance(evento,dict):raise ValueError('Novedad inválida.')
    uid=str(UUID(str(evento.get('uuid',''))))
    ident=int(evento.get('trabajo_id',0));texto=str(evento.get('texto',''))
    if len(texto)>10000:raise ValueError('Máximo 10.000 caracteres por mensaje.')
    accion=evento.get('accion','mensaje')
    if accion not in ('mensaje','iniciar_prueba','sin_observaciones','con_observaciones','describir_observacion','impide_partida','no_impide_partida'):raise ValueError('Acción desconocida.')
    capturado=str(evento.get('capturado',''));datetime.fromisoformat(capturado.replace('Z','+00:00'))
    fotos=[]
    if len(evento.get('fotos',[]))>3:raise ValueError('Máximo tres fotos.')
    for f in evento.get('fotos',[]):
        try:datos=base64.b64decode(f['datos'],validate=True)
        except Exception as exc:raise ValueError('Foto inválida.') from exc
        if len(datos)>2*1024*1024:raise ValueError('Máximo 2 MB por foto.')
        fotos.append((str(f['nombre'])[:240],datos))
    firma=_hash(json.dumps(evento,ensure_ascii=False,sort_keys=True,separators=(',',':')))
    with Session(db.engine) as s,s.begin():
        u,p=_autorizar(s,token)
        if not db.puede_chat(u):raise AccesoInvalido('Solo supervisores, coordinadores o administración pueden sincronizar novedades.')
        p=db._programa(s,u,p.id,True)
        recibo=s.scalar(select(ReciboCampo).where(ReciboCampo.usuario==u['correo'],ReciboCampo.uuid==uid))
        if recibo:
            if recibo.firma!=firma:raise ValueError('El identificador ya corresponde a otra novedad.')
            return dict(ok=True,uuid=uid,repetido=True,version=recibo.version)
        db._editable(s,p.id)
        t=s.get(db.TrabajoFinSemana,ident,with_for_update=True)
        if not t or t.programa!=p.id:raise ValueError('El trabajo no pertenece a esta programación.')
        d=json.loads(t.datos)
        previa=evento.get('prev_uuid')
        anterior=s.scalar(select(ReciboCampo).where(ReciboCampo.usuario==u['correo'],ReciboCampo.uuid==previa,ReciboCampo.trabajo==ident)) if previa else None
        esperado=anterior.version if anterior else int(evento.get('base_version',0))
        conflicto=t.version!=esperado and t.version!=int(evento.get('base_version',0))
        if conflicto and anterior:
            historial=json.loads(t.historial)
            indice=next((i for i,h in enumerate(historial) if h.get('uuid_campo')==anterior.uuid),None)
            posteriores=historial[indice+1:] if indice is not None else []
            if posteriores and all(h.get('automatico') and h.get('usuario')==u['correo'] for h in posteriores):conflicto=False
        cambio={k:d[k] for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba')}
        consulta=None
        if conflicto:
            consulta='El trabajo cambió mientras no había conexión. Se guardó tu novedad; describe el estado actual para actualizar el avance sin reemplazar un registro más reciente.'
        elif accion=='mensaje':
            respuesta=desde_mensaje(d,texto)
            inmediato=directo(texto)
            if respuesta:cambio=respuesta
            elif inmediato:cambio=combinar(d,inmediato)
        else:cambio=transicion(d,accion,texto)
        etiqueta=texto or {'iniciar_prueba':'Se realizaron las pruebas de funcionamiento.','sin_observaciones':'Funcionamiento normal, sin observaciones.','con_observaciones':'Hubo observaciones en las pruebas.','impide_partida':'La observación impide la partida.','no_impide_partida':'La observación no impide la partida ni el funcionamiento normal.'}.get(accion,accion)
        version=db.actualizar(u['correo'],p.id,ident,t.version,cambio,fotos,mensaje=etiqueta,_sesion=s)
        historial=json.loads(t.historial);historial[-1].update(uuid_campo=uid,capturado_dispositivo=capturado)
        t.historial=json.dumps(historial,ensure_ascii=False);s.flush();version=t.version
        if consulta:
            j=db.NovedadIA(trabajo=ident,programa=p.id,usuario=u['correo'],version=version,datos=json.dumps(dict(trabajo=json.loads(t.datos),mensaje=etiqueta),ensure_ascii=False),estado='pregunta',detalle=consulta)
            s.add(j)
        elif accion=='mensaje' and not desde_mensaje(d,texto) and not directo(texto):db.encolar_novedad(u['correo'],p.id,ident,version,texto,_sesion=s)
        s.add(ReciboCampo(usuario=u['correo'],uuid=uid,programa=p.id,trabajo=ident,firma=firma,version=version))
        s.flush()
        return dict(ok=True,uuid=uid,repetido=False,version=version,conflicto=conflicto)
