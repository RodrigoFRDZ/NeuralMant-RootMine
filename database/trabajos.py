"""Programación, bitácora, evidencia y cierres inmutables de turno."""
import hashlib, json
from datetime import datetime
from io import BytesIO
from sqlalchemy import Integer, String, Text, LargeBinary, DateTime, ForeignKey, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column, Session
from PIL import Image
from ia.etapas_trabajos import validar_plan, plan_base, calcular
from database.modelos import Base
from database.conexion import engine
from database.materiales import _usuario

ESTADOS = ['Pendiente', 'En ejecución', 'Detenido', 'Terminado']
ROLES_AVANCE = {'supervisor', 'coordinador_mantenimiento', 'coordinador'}

PRUEBAS = ['Pendiente', 'En prueba', 'Aprobada', 'Fallida', 'No requerida']

class ProgramaFinSemana(Base):
    __tablename__='programa_fin_semana'
    id: Mapped[int]=mapped_column(primary_key=True)
    titulo: Mapped[str]=mapped_column(String(180))
    centro: Mapped[str]=mapped_column(String(40),index=True)
    inicio: Mapped[str]=mapped_column(String(10))
    fin: Mapped[str]=mapped_column(String(10))
    fuente: Mapped[str]=mapped_column(String(240))
    firma: Mapped[str]=mapped_column(String(64),unique=True)
    pdf: Mapped[bytes]=mapped_column(LargeBinary)
    creador: Mapped[str]=mapped_column(String(180))

class TrabajoFinSemana(Base):
    __tablename__='trabajo_fin_semana'
    id: Mapped[int]=mapped_column(primary_key=True)
    programa: Mapped[int]=mapped_column(ForeignKey('programa_fin_semana.id'),index=True)
    datos: Mapped[str]=mapped_column(Text)
    historial: Mapped[str]=mapped_column(Text,default='[]')
    version: Mapped[int]=mapped_column(Integer,default=1,nullable=False)
    __mapper_args__={'version_id_col':version}

class FotoTrabajo(Base):
    __tablename__='foto_trabajo'
    id: Mapped[int]=mapped_column(primary_key=True)
    trabajo: Mapped[int]=mapped_column(ForeignKey('trabajo_fin_semana.id'),index=True)
    contenido: Mapped[bytes]=mapped_column(LargeBinary)
    nombre: Mapped[str]=mapped_column(String(240))
    usuario: Mapped[str]=mapped_column(String(180))
    fecha: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class CierreTrabajo(Base):
    __tablename__='cierre_trabajo'
    id: Mapped[int]=mapped_column(primary_key=True)
    programa: Mapped[int]=mapped_column(ForeignKey('programa_fin_semana.id'),index=True)
    clave: Mapped[str]=mapped_column(String(36),unique=True)
    datos: Mapped[str]=mapped_column(Text)


def gestor(u):
    return bool(u.get('es_admin'))

def puede_publicar(u):
    return bool(u.get('es_admin') or u.get('rol') in ('programador_mantenimiento','programador'))

def puede_chat(u):
    return bool(u.get('es_admin') or u.get('rol') in ROLES_AVANCE)

def _programa(s,u,n,bloquear=False):
    p=s.get(ProgramaFinSemana,n,with_for_update=bloquear)
    if not p or not (u.get('es_admin') or str(u.get('centro'))==p.centro):
        raise ValueError('Este programa no está disponible para tu cuenta.')
    return p

def puede_actualizar(u,d):
    # Center access is checked by _programa before any write. Assignment is informational.
    return puede_chat(u)

def _fila(t):
    return dict(id=t.id,version=t.version,**json.loads(t.datos),historial=json.loads(t.historial))

def programas(correo):
    with Session(engine) as s:
        u=_usuario(s,correo); q=select(ProgramaFinSemana).order_by(ProgramaFinSemana.id.desc())
        if not u.get('es_admin'):q=q.where(ProgramaFinSemana.centro==str(u.get('centro')))
        return [dict(id=p.id,titulo=p.titulo,centro=p.centro,inicio=p.inicio,fin=p.fin,fuente=p.fuente) for p in s.scalars(q)]

def trabajos(correo,n):
    with Session(engine) as s:
        _programa(s,_usuario(s,correo),n)
        return [_fila(t) for t in s.scalars(select(TrabajoFinSemana).where(TrabajoFinSemana.programa==n).order_by(TrabajoFinSemana.id))]

def _validar_plan(s,d,centro):
    for k in ('descripcion','linea','area','supervisor'):
        if not str(d.get(k,'')).strip():raise ValueError('Completa '+k+' en cada trabajo.')
    responsable=_usuario(s,d['supervisor'])
    if responsable.get('rol') not in ROLES_AVANCE or str(responsable.get('centro'))!=centro:
        raise ValueError('Asigna un supervisor o coordinador de mantenimiento activo del centro elegido.')
    resultado={k:str(d.get(k,'')).strip() for k in ('descripcion','linea','area','equipo','supervisor','referencia_pdf','ot','ejecutor','inicio_plan','fin_plan')}
    if d.get('etapas'):resultado['etapas']=validar_plan(d['etapas'])
    return resultado

def crear_programa(correo,titulo,centro,inicio,fin,nombre,pdf,filas):
    from pypdf import PdfReader
    if not titulo.strip() or fin<inicio:raise ValueError('Revisa título y fechas del programa.')
    if not pdf or len(pdf)>10*1024*1024 or not pdf.startswith(b'%PDF'):raise ValueError('Usa un PDF válido de hasta 10 MB.')
    try:
        if len(PdfReader(BytesIO(pdf)).pages)>80:raise ValueError('Máximo 80 páginas por programa.')
    except ValueError:raise
    except Exception as exc:raise ValueError('No se pudo leer el PDF.') from exc
    if not 1<=len(filas)<=300:raise ValueError('Revisa la lista: entre 1 y 300 trabajos.')
    with Session(engine) as s,s.begin():
        u=_usuario(s,correo)
        if not puede_publicar(u) or not (u.get('es_admin') or str(u.get('centro'))==str(centro)):raise ValueError('No puedes publicar este programa.')
        datos=[_validar_plan(s,d,str(centro)) for d in filas]
        firma=hashlib.sha256(pdf+str(centro).encode()+inicio.encode()+fin.encode()).hexdigest()
        anterior=s.scalar(select(ProgramaFinSemana).where(ProgramaFinSemana.firma==firma))
        if anterior:raise ValueError(f'Este PDF ya fue publicado para esas fechas: programa #{anterior.id}.')
        p=ProgramaFinSemana(titulo=titulo.strip(),centro=str(centro),inicio=inicio,fin=fin,fuente=nombre[:240],firma=firma,pdf=pdf,creador=correo)
        s.add(p);s.flush()
        for d in datos:
            d.update(estado='Pendiente',avance=0,pendiente='',hallazgos='',prueba='Pendiente',detalle_prueba='',actualizado='',autor='',fotos=[])
            s.add(TrabajoFinSemana(programa=p.id,datos=json.dumps(d,ensure_ascii=False),historial='[]'))
        return p.id

def actualizar(correo,n,trabajo,version,cambio,fotos=(),mensaje=''):
    if len(mensaje)>10000:raise ValueError('Mensaje demasiado largo.')
    if len(fotos)>3:raise ValueError('Máximo 3 fotos por actualización.')
    for nombre,contenido in fotos:
        if len(contenido)>2*1024*1024:raise ValueError('Cada foto puede pesar hasta 2 MB.')
        try:
            im=Image.open(BytesIO(contenido));formato=im.format;im.verify()
            if formato not in ('JPEG','PNG'):raise ValueError('Usa fotos JPG o PNG.')
        except Exception as exc:raise ValueError('Foto inválida; usa JPG o PNG.') from exc
    estado=cambio.get('estado');avance=cambio.get('avance');prueba=cambio.get('prueba')
    if estado not in ESTADOS or prueba not in PRUEBAS or (avance is not None and (isinstance(avance,bool) or not isinstance(avance,int) or not 0<=avance<=100)):raise ValueError('Estado, avance o prueba inválidos.')
    if (estado=='Terminado') != (avance==100) or (estado=='Pendiente' and avance!=0):raise ValueError('Terminado requiere 100%; Pendiente requiere 0%.')
    if estado=='Detenido' and not cambio.get('pendiente','').strip():raise ValueError('Indica qué está bloqueando el trabajo.')
    if prueba in ('Aprobada','Fallida','No requerida') and not cambio.get('detalle_prueba','').strip():raise ValueError('Registra resultado/evidencia o motivo por el que no requiere prueba.')
    with Session(engine) as s,s.begin():
        u=_usuario(s,correo);_programa(s,u,n,True)
        t=s.get(TrabajoFinSemana,trabajo,with_for_update=True)
        if not t or t.programa!=n:raise ValueError('Trabajo no disponible.')
        d=json.loads(t.datos)
        if not puede_actualizar(u,d):raise ValueError('Solo supervisores, coordinadores de mantenimiento o administración pueden actualizar trabajos del centro.')
        if t.version!=version:raise ValueError('Otro usuario actualizó el trabajo. Recarga antes de guardar; tus datos no se sobrescribieron.')
        if len(d['fotos'])+len(fotos)>12:raise ValueError('Límite de 12 fotos por trabajo.')
        for nombre,contenido in fotos:
            f=FotoTrabajo(trabajo=t.id,nombre=nombre[:240],contenido=contenido,usuario=correo);s.add(f);s.flush();d['fotos'].append(f.id)
        if cambio.get('plan_nuevo'):
            if d.get('etapas'):raise ValueError('El trabajo ya tiene un plan revisado. Recarga la propuesta.')
            d['etapas']=validar_plan(cambio.get('etapas',[]))
            d['plan_origen']='Propuesto por GearBot y confirmado por el responsable de turno'
        origen=cambio.get('origen_avance')
        if origen=='estimado_etapas':
            plan=d.get('etapas') or plan_base(d['descripcion'])
            if not plan:raise ValueError('Administración debe revisar el plan de etapas antes de estimar este trabajo.')
            esperado,cerradas=calcular(plan,[],cambio.get('etapas_confirmadas',[]),[])
            if esperado!=avance:raise ValueError('El porcentaje no coincide con las etapas confirmadas.')
            d.update(etapas=plan,etapas_confirmadas=cerradas,origen_avance=origen)
        elif origen is not None:
            if origen not in ('informado_supervisor','estado_supervisor'):raise ValueError('Origen del avance inválido.')
            d['origen_avance']=origen
        for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba'):d[k]=cambio.get(k,'')
        d.update(actualizado=datetime.utcnow().isoformat(),autor=correo)
        if mensaje.strip():d['ultimo_mensaje']=mensaje.strip()
        h=json.loads(t.historial);h.append(dict(origen_avance=d.get('origen_avance','informado_supervisor'),etapas_confirmadas=d.get('etapas_confirmadas',[]),mensaje=mensaje.strip(),fecha=d['actualizado'],usuario=correo,nombre=u['nombre'],**{k:d[k] for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba')},fotos=list(d['fotos'])))
        t.datos=json.dumps(d,ensure_ascii=False);t.historial=json.dumps(h,ensure_ascii=False)
        s.flush()
        return t.version

def evidencia(correo,n,trabajo):
    with Session(engine) as s:
        _programa(s,_usuario(s,correo),n)
        t=s.get(TrabajoFinSemana,trabajo)
        if not t or t.programa!=n:raise ValueError('Trabajo no disponible.')
        return [dict(id=f.id,nombre=f.nombre,contenido=f.contenido,usuario=f.usuario,fecha=f.fecha) for f in s.scalars(select(FotoTrabajo).where(FotoTrabajo.trabajo==trabajo).order_by(FotoTrabajo.id))]

def fuente(correo,n):
    with Session(engine) as s:
        p=_programa(s,_usuario(s,correo),n);return p.pdf

def lineas(filas):
    resultado=[]
    for linea in sorted({d['linea'] for d in filas}):
        grupo=[d for d in filas if d['linea']==linea]
        terminados=all(d['estado']=='Terminado' for d in grupo)
        pruebas=all(d['prueba'] in ('Aprobada','No requerida') for d in grupo)
        bloqueos=any(d['pendiente'].strip() for d in grupo)
        lista=terminados and pruebas and not bloqueos
        resultado.append(dict(línea=linea,trabajos=len(grupo),avance=round(sum(d['avance'] for d in grupo if d['avance'] is not None)/sum(d['avance'] is not None for d in grupo),1) if any(d['avance'] is not None for d in grupo) else None,sin_porcentaje=sum(d['avance'] is None for d in grupo),partida='Lista según registros' if lista else 'Pendiente',pruebas='Verificadas / no requeridas documentadas' if pruebas else 'Pruebas pendientes o fallidas'))
    return resultado

def cerrar_turno(correo,n,fecha,turno,comentario,clave):
    if turno not in ('Día','Noche'):raise ValueError('Turno inválido.')
    with Session(engine) as s,s.begin():
        u=_usuario(s,correo);p=_programa(s,u,n,True)
        if not puede_chat(u):raise ValueError('No puedes registrar cierres de turno.')
        previo=s.scalar(select(CierreTrabajo).where(CierreTrabajo.clave==clave))
        if previo:
            if previo.programa!=n:raise ValueError('Clave de cierre inválida.')
            return previo.id
        filas=[_fila(t) for t in s.scalars(select(TrabajoFinSemana).where(TrabajoFinSemana.programa==n).order_by(TrabajoFinSemana.id))]
        datos=dict(titulo=p.titulo,centro=p.centro,fecha=fecha,turno=turno,comentario=comentario,autor=correo,nombre=u['nombre'],generado=datetime.utcnow().isoformat(),trabajos=filas,lineas=lineas(filas))
        cierre=CierreTrabajo(programa=n,clave=clave,datos=json.dumps(datos,ensure_ascii=False));s.add(cierre);s.flush();return cierre.id

def cierres(correo,n):
    with Session(engine) as s:
        _programa(s,_usuario(s,correo),n)
        return [dict(id=c.id,**json.loads(c.datos)) for c in s.scalars(select(CierreTrabajo).where(CierreTrabajo.programa==n).order_by(CierreTrabajo.id.desc()))]

def reasignar(correo,n,trabajo,version,supervisor):
    with Session(engine) as s,s.begin():
        u=_usuario(s,correo);p=_programa(s,u,n,True)
        if not gestor(u):raise ValueError('Solo gestión puede reasignar el trabajo.')
        t=s.get(TrabajoFinSemana,trabajo,with_for_update=True)
        if not t or t.programa!=n:raise ValueError('Trabajo no disponible.')
        if t.version!=version:raise ValueError('El trabajo cambió. Recarga antes de reasignar.')
        d=json.loads(t.datos);_validar_plan(s,d|{'supervisor':supervisor},p.centro)
        anterior=d['supervisor'];d['supervisor']=supervisor
        d.update(actualizado=datetime.utcnow().isoformat(),autor=correo)
        h=json.loads(t.historial);h.append(dict(fecha=d['actualizado'],usuario=correo,nombre=u['nombre'],**{k:d[k] for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba')},fotos=list(d['fotos']),reasignacion=f'{anterior} → {supervisor}'))
        t.datos=json.dumps(d,ensure_ascii=False);t.historial=json.dumps(h,ensure_ascii=False)


def configurar_etapas(correo,n,trabajo,version,plan):
    plan=validar_plan(plan)
    with Session(engine) as s,s.begin():
        u=_usuario(s,correo);_programa(s,u,n,True)
        if not gestor(u):raise ValueError('Solo administración puede revisar las etapas después de publicar.')
        t=s.get(TrabajoFinSemana,trabajo,with_for_update=True)
        if not t or t.programa!=n or t.version!=version:raise ValueError('El trabajo cambió. Recarga antes de guardar el plan.')
        d=json.loads(t.datos)
        if d.get('etapas_confirmadas'):raise ValueError('Este plan ya tiene etapas confirmadas; no se modifican sus pesos durante la ejecución.')
        d['etapas']=plan;t.datos=json.dumps(d,ensure_ascii=False)
