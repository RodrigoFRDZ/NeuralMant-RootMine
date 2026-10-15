"""Programación, bitácora, evidencia y cierres inmutables de turno."""
import hashlib, json, calendar, logging, threading
from contextlib import ExitStack
from datetime import datetime, date, timedelta
from io import BytesIO
from sqlalchemy import Integer, String, Text, LargeBinary, DateTime, ForeignKey, UniqueConstraint, select, delete, or_, and_, func
from sqlalchemy.orm import Mapped, mapped_column, Session, defer
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


class HistoricoTrabajo(Base):
    __tablename__='historico_trabajo'
    programa: Mapped[int]=mapped_column(ForeignKey('programa_fin_semana.id'),primary_key=True)
    pdf: Mapped[bytes]=mapped_column(LargeBinary)
    cerrado: Mapped[datetime]=mapped_column(DateTime)
    vence: Mapped[datetime]=mapped_column(DateTime,index=True)


class NovedadIA(Base):
    __tablename__='novedad_trabajo_ia'
    id: Mapped[int]=mapped_column(primary_key=True)
    trabajo: Mapped[int]=mapped_column(ForeignKey('trabajo_fin_semana.id'),index=True)
    programa: Mapped[int]=mapped_column(ForeignKey('programa_fin_semana.id'),index=True)
    usuario: Mapped[str]=mapped_column(String(180))
    version: Mapped[int]=mapped_column(Integer)
    datos: Mapped[str]=mapped_column(Text)
    estado: Mapped[str]=mapped_column(String(30),default='pendiente',index=True)
    detalle: Mapped[str]=mapped_column(Text,default='')
    token: Mapped[str]=mapped_column(String(36),default='')
    actualizado: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)


class NovedadArea(Base):
    __tablename__='novedad_area_trabajo'
    id: Mapped[int]=mapped_column(primary_key=True)
    programa: Mapped[int]=mapped_column(ForeignKey('programa_fin_semana.id'),index=True)
    clave: Mapped[str]=mapped_column(String(36),unique=True)
    firma: Mapped[str]=mapped_column(String(64))
    area: Mapped[str]=mapped_column(String(180))
    datos: Mapped[str]=mapped_column(Text)


def _tres_meses(fecha):
    mes=fecha.month+3;anio=fecha.year+(mes-1)//12;mes=(mes-1)%12+1
    return fecha.replace(year=anio,month=mes,day=min(fecha.day,calendar.monthrange(anio,mes)[1]))

def _limpiar_historial(s,ahora):
    vencidos=list(s.scalars(select(HistoricoTrabajo).options(defer(HistoricoTrabajo.pdf)).where(HistoricoTrabajo.vence<=ahora).with_for_update()))
    for h in vencidos:
        n=h.programa
        from database.campo import AccesoCampo, ReciboCampo
        s.execute(delete(AccesoCampo).where(AccesoCampo.programa==n))
        s.execute(delete(ReciboCampo).where(ReciboCampo.programa==n))
        s.delete(h);s.flush()
        s.execute(delete(ProgramaFinSemana).where(ProgramaFinSemana.id==n))
    return len(vencidos)

def limpiar_historial():
    with Session(engine) as s,s.begin():return _limpiar_historial(s,datetime.utcnow())


_limpieza_lock=threading.Lock()
_limpieza_iniciada=False

def iniciar_limpieza_historial():
    """Hourly cleanup while the Streamlit process is running; reads also clean on wake-up."""
    global _limpieza_iniciada
    with _limpieza_lock:
        if _limpieza_iniciada:return
        _limpieza_iniciada=True
    def tarea():
        espera=threading.Event()
        while True:
            try:limpiar_historial()
            except Exception:logging.getLogger(__name__).exception('No se pudo limpiar el histórico de trabajos')
            espera.wait(3600)
    threading.Thread(target=tarea,name='limpieza-historico-trabajos',daemon=True).start()

def _editable(s,n):
    if s.scalar(select(HistoricoTrabajo.programa).where(HistoricoTrabajo.programa==n)):raise ValueError('Este programa está cerrado. Consulta o descarga su PDF histórico.')

def _archivar(s,p,u):
    from reportes.trabajos import render_pdf
    if s.get(HistoricoTrabajo,p.id):return
    filas=[_fila(t) for t in s.scalars(select(TrabajoFinSemana).where(TrabajoFinSemana.programa==p.id).order_by(TrabajoFinSemana.id))]
    entregas=[json.loads(c.datos) for c in s.scalars(select(CierreTrabajo).where(CierreTrabajo.programa==p.id).order_by(CierreTrabajo.id))]
    from database.novedades_area import _listar
    novedades_area=_listar(s,p.id)
    fotos={}
    for d in filas:
        fotos[d['id']]=[]
        for f in s.scalars(select(FotoTrabajo).where(FotoTrabajo.trabajo==d['id']).order_by(FotoTrabajo.id)):
            # Keep photographic evidence inside the final PDF, at a bounded display resolution.
            imagen=Image.open(BytesIO(f.contenido)).convert('RGB');imagen.thumbnail((1000,1000))
            out=BytesIO();imagen.save(out,format='JPEG',quality=70)
            fotos[d['id']].append(dict(contenido=out.getvalue(),nombre=f.nombre,usuario=f.usuario,fecha=f.fecha))
    ahora=datetime.utcnow()
    sin_procesar=[f"Trabajo #{j.trabajo}: {j.estado} · {j.detalle or 'Procesamiento sin terminar'}" for j in s.scalars(select(NovedadIA).where(NovedadIA.programa==p.id,NovedadIA.estado.in_(['pendiente','procesando','pregunta','error'])))]
    nota_ia='\nNovedades con procesamiento o aclaración pendiente:\n'+'\n'.join(sin_procesar) if sin_procesar else ''
    corte=dict(titulo=p.titulo,centro=p.centro,fecha=p.inicio+' a '+p.fin,turno='Informe final',comentario='Cerrado automáticamente al publicar la siguiente programación. Los estados reflejan lo registrado; los trabajos pendientes no se marcan terminados.'+nota_ia,sugerencias='\n'.join(f"{e['nombre']}: {e['sugerencias']}" for e in entregas if e.get('sugerencias')),autor=u['correo'],nombre=u['nombre'],generado=ahora.isoformat(),trabajos=filas,lineas=lineas(filas),novedades_area=novedades_area,entregas=entregas,final=True)
    from ia.resumen_turno import resumen_base
    sintesis=resumen_base(filas,novedades_area)
    corte['comentario']=sintesis['comentario']+nota_ia
    corte['sugerencias_automaticas']=False
    pdf=render_pdf(corte,fotos)
    s.add(HistoricoTrabajo(programa=p.id,pdf=pdf,cerrado=ahora,vence=_tres_meses(ahora)));s.flush()
    ids=select(TrabajoFinSemana.id).where(TrabajoFinSemana.programa==p.id)
    s.execute(delete(NovedadArea).where(NovedadArea.programa==p.id))
    s.execute(delete(NovedadIA).where(NovedadIA.programa==p.id))
    s.execute(delete(FotoTrabajo).where(FotoTrabajo.trabajo.in_(ids)))
    s.execute(delete(CierreTrabajo).where(CierreTrabajo.programa==p.id))
    s.execute(delete(TrabajoFinSemana).where(TrabajoFinSemana.programa==p.id))
    p.pdf=b''  # Only the final report and minimal index metadata remain.

def historico_pdf(correo,n):
    with Session(engine) as s,s.begin():
        u=_usuario(s,correo);_limpiar_historial(s,datetime.utcnow());_programa(s,u,n)
        h=s.get(HistoricoTrabajo,n)
        if not h:raise ValueError('No hay PDF histórico para este programa.')
        return h.pdf


def gestor(u):
    return bool(u.get('es_admin'))

def puede_publicar(u):
    return bool(u.get('es_admin') or u.get('rol') in ('programador_mantenimiento','programador'))

def puede_chat(u):
    return bool(u.get('es_admin') or u.get('rol') in ROLES_AVANCE)

def _programa(s,u,n,bloquear=False):
    p=s.get(ProgramaFinSemana,n,options=[defer(ProgramaFinSemana.pdf)],with_for_update=bloquear)
    if not p or not (u.get('es_admin') or str(u.get('centro'))==p.centro):
        raise ValueError('Este programa no está disponible para tu cuenta.')
    return p

def puede_actualizar(u,d):
    # Center access is checked by _programa before any write. Assignment is informational.
    return puede_chat(u)

def _fila(t):
    return dict(id=t.id,version=t.version,**json.loads(t.datos),historial=json.loads(t.historial))

def programas(correo):
    with Session(engine) as s,s.begin():
        u=_usuario(s,correo);_limpiar_historial(s,datetime.utcnow())
        # Navigation needs metadata only, never the original or archived PDF bytes.
        q=select(ProgramaFinSemana.id,ProgramaFinSemana.titulo,ProgramaFinSemana.centro,
            ProgramaFinSemana.inicio,ProgramaFinSemana.fin,ProgramaFinSemana.fuente,HistoricoTrabajo.vence).outerjoin(
            HistoricoTrabajo,HistoricoTrabajo.programa==ProgramaFinSemana.id).order_by(ProgramaFinSemana.id.desc())
        if not u.get('es_admin'):q=q.where(ProgramaFinSemana.centro==str(u.get('centro')))
        return [dict(id=p.id,titulo=p.titulo,centro=p.centro,inicio=p.inicio,fin=p.fin,fuente=p.fuente,
            cerrado=p.vence is not None,vence=p.vence.isoformat() if p.vence else '') for p in s.execute(q)]

def trabajos(correo,n):
    with Session(engine) as s:
        _programa(s,_usuario(s,correo),n)
        return [_fila(t) for t in s.scalars(select(TrabajoFinSemana).where(TrabajoFinSemana.programa==n).order_by(TrabajoFinSemana.id))]

def _validar_plan(s,d,centro):
    for k in ('descripcion','area'):
        if not str(d.get(k,'')).strip():raise ValueError('Completa '+k+' en cada trabajo.')
    resultado={k:str(d.get(k,'')).strip() for k in ('descripcion','linea','area','equipo','referencia_pdf','ot','ejecutor','inicio_plan','fin_plan')}
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
        _limpiar_historial(s,datetime.utcnow())
        datos=[_validar_plan(s,d,str(centro)) for d in filas]
        firma=hashlib.sha256(pdf+str(centro).encode()+inicio.encode()+fin.encode()).hexdigest()
        anterior=s.scalar(select(ProgramaFinSemana).where(ProgramaFinSemana.firma==firma))
        if anterior:raise ValueError(f'Este PDF ya fue publicado para esas fechas: programa #{anterior.id}.')
        # Lock a stable center row, including the first publication, to serialize publishers.
        from database.modelos import UsuarioRootMine
        s.scalar(select(UsuarioRootMine).where(UsuarioRootMine.centro==str(centro)).order_by(UsuarioRootMine.id).limit(1).with_for_update())
        previos=list(s.scalars(select(ProgramaFinSemana).where(ProgramaFinSemana.centro==str(centro)).order_by(ProgramaFinSemana.id).with_for_update()))
        abiertos=[previo for previo in previos if not s.get(HistoricoTrabajo,previo.id)]
        if abiertos and inicio<=max(previo.inicio for previo in abiertos):
            raise ValueError('La nueva programación debe comenzar después de la programación vigente.')
        for previo in abiertos:_archivar(s,previo,u)
        p=ProgramaFinSemana(titulo=titulo.strip(),centro=str(centro),inicio=inicio,fin=fin,fuente=nombre[:240],firma=firma,pdf=pdf,creador=correo)
        s.add(p);s.flush()
        for d in datos:
            d.update(estado='Pendiente',avance=0,pendiente='',hallazgos='',prueba='Pendiente',detalle_prueba='',actualizado='',autor='',fotos=[])
            s.add(TrabajoFinSemana(programa=p.id,datos=json.dumps(d,ensure_ascii=False),historial='[]'))
        return p.id

def actualizar(correo,n,trabajo,version,cambio,fotos=(),mensaje='',_sesion=None):
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
    with ExitStack() as stack:
        if _sesion is not None:s=_sesion
        else:
            s=stack.enter_context(Session(engine));stack.enter_context(s.begin())
        u=_usuario(s,correo);_programa(s,u,n,True);_editable(s,n)
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
            d['plan_origen']='Plan orientativo generado automáticamente por GearBot' if cambio.get('aplicacion_automatica') else 'Propuesto por GearBot y confirmado por el responsable de turno'
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
        recien_terminado=d.get('estado')!='Terminado' and estado=='Terminado'
        for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba'):d[k]=cambio.get(k,'')
        if 'dialogo_prueba' in cambio:d['dialogo_prueba']=cambio['dialogo_prueba']
        if recien_terminado and d['prueba']=='Pendiente':d['dialogo_prueba']={'paso':'realizacion'}
        d.update(actualizado=datetime.utcnow().isoformat(),autor=correo)
        if mensaje.strip():d['ultimo_mensaje']=mensaje.strip()
        h=json.loads(t.historial);h.append(dict(automatico=bool(cambio.get('aplicacion_automatica')),origen_avance=d.get('origen_avance','informado_supervisor'),etapas_confirmadas=d.get('etapas_confirmadas',[]),mensaje=mensaje.strip(),fecha=d['actualizado'],usuario=correo,nombre=u['nombre'],rol=u.get('rol',''),**{k:d[k] for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba')},fotos=list(d['fotos'])))
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
    for area,linea in sorted({(d['area'],d.get('linea') or '') for d in filas}):
        grupo=[d for d in filas if d['area']==area and (d.get('linea') or '')==linea]
        terminados=all(d['estado']=='Terminado' for d in grupo)
        pruebas=all(d['prueba'] in ('Aprobada','No requerida') for d in grupo)
        bloqueos=any(d['pendiente'].strip() for d in grupo)
        lista=terminados and pruebas and not bloqueos
        resultado.append(dict(línea=area+' · '+(linea or 'Sin línea informada'),trabajos=len(grupo),avance=round(sum(d['avance'] for d in grupo if d['avance'] is not None)/sum(d['avance'] is not None for d in grupo),1) if any(d['avance'] is not None for d in grupo) else None,sin_porcentaje=sum(d['avance'] is None for d in grupo),partida='Lista según registros' if lista else 'Pendiente',pruebas='Verificadas / no requeridas documentadas' if pruebas else 'Pruebas pendientes o fallidas'))
    return resultado

def cerrar_turno(correo,n,fecha,turno,comentario,clave,sugerencias=""):
    if turno not in ('Día','Noche'):raise ValueError('Turno inválido.')
    with Session(engine) as s,s.begin():
        u=_usuario(s,correo);p=_programa(s,u,n,True);_editable(s,n)
        if not puede_chat(u):raise ValueError('No puedes registrar cierres de turno.')
        previo=s.scalar(select(CierreTrabajo).where(CierreTrabajo.clave==clave))
        if previo:
            if previo.programa!=n:raise ValueError('Clave de cierre inválida.')
            return previo.id
        filas=[_fila(t) for t in s.scalars(select(TrabajoFinSemana).where(TrabajoFinSemana.programa==n).order_by(TrabajoFinSemana.id))]
        datos=dict(titulo=p.titulo,centro=p.centro,fecha=fecha,turno=turno,comentario=comentario,sugerencias=sugerencias,autor=correo,nombre=u['nombre'],generado=datetime.utcnow().isoformat(),trabajos=filas,lineas=lineas(filas))
        cierre=CierreTrabajo(programa=n,clave=clave,datos=json.dumps(datos,ensure_ascii=False));s.add(cierre);s.flush();return cierre.id

def cierres(correo,n):
    with Session(engine) as s:
        _programa(s,_usuario(s,correo),n)
        return [dict(id=c.id,**json.loads(c.datos)) for c in s.scalars(select(CierreTrabajo).where(CierreTrabajo.programa==n).order_by(CierreTrabajo.id.desc()))]

def configurar_etapas(correo,n,trabajo,version,plan):
    plan=validar_plan(plan)
    with Session(engine) as s,s.begin():
        u=_usuario(s,correo);_programa(s,u,n,True);_editable(s,n)
        if not gestor(u):raise ValueError('Solo administración puede revisar las etapas después de publicar.')
        t=s.get(TrabajoFinSemana,trabajo,with_for_update=True)
        if not t or t.programa!=n or t.version!=version:raise ValueError('El trabajo cambió. Recarga antes de guardar el plan.')
        d=json.loads(t.datos)
        if d.get('etapas_confirmadas'):raise ValueError('Este plan ya tiene etapas confirmadas; no se modifican sus pesos durante la ejecución.')
        d['etapas']=plan;t.datos=json.dumps(d,ensure_ascii=False)


def encolar_novedad(correo,n,ident,version,mensaje,_sesion=None):
    with ExitStack() as stack:
        if _sesion is not None:s=_sesion
        else:
            s=stack.enter_context(Session(engine));stack.enter_context(s.begin())
        u=_usuario(s,correo);_programa(s,u,n,True);_editable(s,n)
        t=s.get(TrabajoFinSemana,ident)
        if not t or t.programa!=n or not puede_chat(u):raise ValueError('Trabajo no disponible para actualizar.')
        if t.version!=version:raise ValueError('La novedad se guardó, pero otra persona actualizó el trabajo. GearBot no sobrescribirá su avance.')
        anterior=s.scalar(select(NovedadIA).where(NovedadIA.trabajo==ident,NovedadIA.estado=='pregunta').order_by(NovedadIA.id.desc()))
        historial=json.loads(t.historial)
        contexto='\n'.join(h['mensaje'] for h in historial[-6:] if h.get('mensaje'))
        if anterior:
            previo=json.loads(anterior.datos)
            contexto=previo.get('contexto','')+'\n'+previo['mensaje']+'\nGearBot preguntó: '+anterior.detalle
            anterior.estado='respondida'
        for viejo in s.scalars(select(NovedadIA).where(NovedadIA.trabajo==ident,NovedadIA.estado.in_(['pendiente','procesando','pregunta']))):
            viejo.estado='respondida';viejo.token=''
        job=NovedadIA(trabajo=ident,programa=n,usuario=correo,version=version,datos=json.dumps(dict(trabajo=json.loads(t.datos),mensaje=mensaje,contexto=contexto),ensure_ascii=False),estado='pendiente',detalle='')
        s.add(job);s.flush();return job.id


_novedad_claim_lock=threading.Lock()

def tomar_novedad():
    with _novedad_claim_lock:return _tomar_novedad()

def _tomar_novedad():
    from uuid import uuid4
    with Session(engine) as s,s.begin():
        ahora=datetime.utcnow()
        j=s.scalar(select(NovedadIA).where(or_(NovedadIA.estado=='pendiente',and_(NovedadIA.estado=='procesando',NovedadIA.actualizado<ahora-timedelta(minutes=2)))).order_by(NovedadIA.id).limit(1).with_for_update(skip_locked=True))
        if not j:return None
        j.estado='procesando';j.actualizado=ahora;j.token=str(uuid4())
        return dict(id=j.id,token=j.token,usuario=j.usuario,programa=j.programa,ident=j.trabajo,version=j.version,**json.loads(j.datos))


def resultado_novedad(job,propuesta=None,error=''):
    from ia.novedad_automatica import combinar
    # Apply with the version captured AFTER saving the message; a newer edit wins.
    with Session(engine) as s:
        j=s.get(NovedadIA,job['id'])
        if not j or j.token!=job['token'] or j.estado!='procesando':return
        t=s.get(TrabajoFinSemana,job['ident'])
        if not t or t.version!=job['version']:error='El trabajo recibió una actualización más reciente. Se conservó la novedad y no se sobrescribió el avance.'
    detalle=error;estado='error' if error else 'lista'
    if not error:
        if propuesta.get('pregunta'):estado='pregunta';detalle=propuesta['pregunta']
        else:
            cambio=combinar(job['trabajo'],propuesta)
            cambio['aplicacion_automatica']=True
            if cambio.get('pregunta'):estado='pregunta';detalle=cambio['pregunta']
            else:
                try:
                    actualizar(job['usuario'],job['programa'],job['ident'],job['version'],cambio)
                    detalle='Avance actualizado automáticamente según tu novedad.'
                except ValueError as exc:estado='error';detalle=str(exc)
    with Session(engine) as s,s.begin():
        j=s.get(NovedadIA,job['id'],with_for_update=True)
        if j and j.token==job['token']:
            j.estado=estado;j.detalle=detalle;j.actualizado=datetime.utcnow()


def ultima_novedad(correo,n,ident):
    with Session(engine) as s:
        _programa(s,_usuario(s,correo),n)
        j=s.execute(select(NovedadIA.id,NovedadIA.estado,NovedadIA.detalle).where(NovedadIA.programa==n,NovedadIA.trabajo==ident).order_by(NovedadIA.id.desc()).limit(1)).first()
        return dict(id=j.id,estado=j.estado,detalle=j.detalle) if j else None


def descartar_novedades_anteriores(correo,n,ident):
    with Session(engine) as s,s.begin():
        u=_usuario(s,correo);_programa(s,u,n,True);_editable(s,n)
        if not puede_chat(u):raise ValueError('No puedes actualizar este programa.')
        for j in s.scalars(select(NovedadIA).where(NovedadIA.programa==n,NovedadIA.trabajo==ident,NovedadIA.estado.in_(['pendiente','procesando','pregunta']))):
            j.estado='respondida';j.token=''


def registrar_prueba(correo,n,ident,version,accion,texto=''):
    from motores.pruebas_trabajos import transicion
    with Session(engine) as s,s.begin():
        u=_usuario(s,correo);_programa(s,u,n,True);_editable(s,n)
        t=s.get(TrabajoFinSemana,ident)
        if not t or t.programa!=n:raise ValueError('Trabajo no disponible.')
        cambio=transicion(json.loads(t.datos),accion,texto)
        return actualizar(correo,n,ident,version,cambio,mensaje=texto or {'posponer_prueba':'Las pruebas de funcionamiento aún no se han realizado. Quedan pendientes de validación.','iniciar_prueba':'Se realizaron las pruebas de funcionamiento.','sin_observaciones':'Funcionamiento normal, sin observaciones.','con_observaciones':'Se observaron anomalías durante la prueba.','impide_partida':'La observación impide la partida.','no_impide_partida':'La observación no impide la partida ni el funcionamiento normal.'}.get(accion,accion),_sesion=s)
