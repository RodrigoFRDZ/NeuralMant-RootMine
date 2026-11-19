"""Historial de fallas SAP. No guarda archivos Excel originales."""
from __future__ import annotations
import datetime as dt
import re
import json
from pathlib import Path
import unicodedata
from collections import defaultdict
from sqlalchemy import String, Integer, Float, Date, DateTime, Text, select, func
from sqlalchemy.orm import Mapped, mapped_column, Session
from database.modelos import Base, ADF
from database.conexion import engine

class AvisoFalla(Base):
    __tablename__ = 'historial_aviso_falla'
    aviso: Mapped[str] = mapped_column(String(40), primary_key=True)
    orden: Mapped[str] = mapped_column(String(40), default='')
    fecha: Mapped[dt.date] = mapped_column(Date, index=True)
    equipo_codigo: Mapped[str] = mapped_column(String(80), index=True)
    equipo_nombre: Mapped[str] = mapped_column(String(250), default='')
    area: Mapped[str] = mapped_column(String(120), index=True)
    centro_costo: Mapped[str] = mapped_column(String(80), default='', index=True)
    ubicacion: Mapped[str] = mapped_column(String(250), default='')
    descripcion: Mapped[str] = mapped_column(Text, default='')
    texto: Mapped[str] = mapped_column(Text, default='')
    tp_min: Mapped[float] = mapped_column(Float, default=0)
    modo: Mapped[str] = mapped_column(String(120), default='')
    importado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

class ExcepcionADF(Base):
    __tablename__ = 'historial_excepcion_adf'
    aviso: Mapped[str] = mapped_column(String(40), primary_key=True)
    causa: Mapped[str] = mapped_column(Text)
    justificacion: Mapped[str] = mapped_column(Text)
    accion: Mapped[str] = mapped_column(Text, default='')
    responsable: Mapped[str] = mapped_column(String(180))
    fecha: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

class SeguimientoADF(Base):
    __tablename__ = 'historial_seguimiento_adf'
    adf_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plazo_dias: Mapped[int] = mapped_column(Integer)
    fundamento: Mapped[str] = mapped_column(Text)
    confianza: Mapped[str] = mapped_column(String(30), default='baja')
    inicio: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    evidencia_validada: Mapped[str] = mapped_column(Text, default='')
    calculado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

class ImportacionHistorial(Base):
    __tablename__ = 'historial_importacion'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fecha: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    responsable: Mapped[str] = mapped_column(String(180))
    nuevos: Mapped[int] = mapped_column(Integer)
    actualizados: Mapped[int] = mapped_column(Integer)
    rechazados: Mapped[int] = mapped_column(Integer)
    max_fecha: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

def crear_tablas_historial():
    Base.metadata.create_all(engine, tables=[AvisoFalla.__table__,ExcepcionADF.__table__,SeguimientoADF.__table__,ImportacionHistorial.__table__])
    if engine.dialect.name == 'postgresql':
        from sqlalchemy import text
        with engine.begin() as c:
            c.execute(text("ALTER TABLE historial_aviso_falla ADD COLUMN IF NOT EXISTS centro_costo VARCHAR(80) DEFAULT ''"))
            for tabla in ('historial_aviso_falla','historial_excepcion_adf','historial_seguimiento_adf','historial_importacion'):
                c.execute(text(f'ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY'))

def limpio(s):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(s or '').lower()) if not unicodedata.combining(c))

PATRONES = {
    'Ingreso de agua': ('ingreso de agua','entra agua','mojado','humedad','inundacion'),
    'Objeto extraño / atrapamiento': ('atrapad','herramienta','objeto extrano','cuerpo extrano'),
    'Sellado': ('sellador','mordaza','sellado','sellante'),
    'Neumática': ('neumat','electrovalvula','cilindro','presion aire'),
    'Transmisión / eje': ('eje','rodamiento','cadena','correa','reductor'),
    'Eléctrica': ('motor quemado','cortocircuito','contactor','variador','electrico'),
    'Sensores / control': ('sensor','fotocelda','encoder','plc'),
}
def clasificar(texto):
    t=limpio(texto)
    hallados=[(sum(k in t for k in claves),modo) for modo,claves in PATRONES.items()]
    puntuacion,modo=max(hallados,default=(0,''))
    return modo if puntuacion else 'Sin clasificar'

def fecha_excel(v):
    if isinstance(v,dt.datetime): return v.date()
    if isinstance(v,dt.date): return v
    if isinstance(v,(int,float)):
        return (dt.datetime(1899,12,30)+dt.timedelta(days=float(v))).date()
    s=str(v or '').strip()
    for f in ('%d.%m.%Y','%d/%m/%Y','%Y-%m-%d','%Y-%m-%d %H:%M:%S'):
        try:return dt.datetime.strptime(s,f).date()
        except ValueError:pass
    raise ValueError('Fecha no reconocida')

def area_por_ceco(centro):
    """Mapeo mantenido desde el archivo Datos por CeCo. Sin coincidencia no se inventa área."""
    archivo = Path(__file__).with_name('centros_costo_areas.json')
    try:
        with archivo.open(encoding='utf-8') as f:
            tabla = json.load(f)
    except (OSError, ValueError):
        return 'Sin área asignada'
    return tabla.get(str(centro or '').strip().upper(), 'Sin área asignada')

def procesar_excel(archivo, responsable, confirmar=False):
    # El archivo se lee en memoria y nunca se escribe a disco.
    from openpyxl import load_workbook
    libro=load_workbook(archivo,read_only=True,data_only=True)
    hoja=libro.active
    filas=hoja.iter_rows(values_only=True)
    cab=[str(x or '').strip() for x in next(filas)]
    def idx(nombre,ocurrencia=0):
        coincidencias=[i for i,x in enumerate(cab) if x==nombre]
        if len(coincidencias)<=ocurrencia:raise ValueError(f'Falta columna SAP: {nombre}')
        return coincidencias[ocurrencia]
    cols={k:idx(k) for k in ['Notificación','Fe.notif.','Equipo','Indicador ABC','Duración parada','Unidad','Ubicac.técnica']}
    nombre_equipo=idx('Descripción',1)
    desc_aviso=idx('Descripción',0)
    ceco_idx=idx('Centro coste')
    orden_idx=idx('Orden')
    texto_idx=idx('Texto completo del aviso')
    registros={};errores=[]
    for numero,fila in enumerate(filas,start=2):
        try:
            if str(fila[cols['Indicador ABC']] or '').strip().upper()!='A':continue
            aviso=str(fila[cols['Notificación']] or '').strip()
            if not aviso:raise ValueError('Aviso vacío')
            unidad=str(fila[cols['Unidad']] or 'H').strip().upper()
            dur=float(fila[cols['Duración parada']] or 0)
            if unidad in ('H','HR','HOR'):dur*=60
            elif unidad in ('MIN','M'):pass
            else:raise ValueError(f'Unidad TP desconocida: {unidad}')
            desc=str(fila[desc_aviso] or '')
            texto=str(fila[texto_idx] or '')
            registros[aviso]=dict(aviso=aviso,orden=str(fila[orden_idx] or ''),fecha=fecha_excel(fila[cols['Fe.notif.']]),equipo_codigo=str(fila[cols['Equipo']] or ''),equipo_nombre=str(fila[nombre_equipo] or ''),area=area_por_ceco(fila[ceco_idx]),centro_costo=str(fila[ceco_idx] or '').strip().upper(),ubicacion=str(fila[cols['Ubicac.técnica']] or ''),descripcion=desc,texto=texto,tp_min=round(dur,2),modo=clasificar(desc+' '+texto))
        except Exception as e:errores.append(f'Fila {numero}: {e}')
    libro.close()
    if not confirmar:return dict(registros=len(registros),rechazados=len(errores),errores=errores[:20])
    nuevos=actualizados=0
    with Session(engine) as s:
        for aviso,d in registros.items():
            existente=s.get(AvisoFalla,aviso)
            if existente:
                for k,v in d.items():setattr(existente,k,v)
                existente.importado_en=dt.datetime.utcnow();actualizados+=1
            else:s.add(AvisoFalla(**d));nuevos+=1
        s.add(ImportacionHistorial(responsable=responsable,nuevos=nuevos,actualizados=actualizados,rechazados=len(errores),max_fecha=max((r['fecha'] for r in registros.values()),default=None)))
        s.commit()
    return dict(nuevos=nuevos,actualizados=actualizados,rechazados=len(errores),errores=errores[:20])

def datos():
    with Session(engine) as s:
        avisos=s.scalars(select(AvisoFalla).order_by(AvisoFalla.fecha)).all()
        adfs=s.scalars(select(ADF)).all()
        excepciones={x.aviso:x for x in s.scalars(select(ExcepcionADF)).all()}
        seguimientos={x.adf_id:x for x in s.scalars(select(SeguimientoADF)).all()}
        ultima=s.scalar(select(func.max(ImportacionHistorial.max_fecha)))
        for aviso in avisos:
            aviso.area = area_por_ceco(aviso.centro_costo) if aviso.centro_costo else 'Sin área asignada'
        return avisos,adfs,excepciones,seguimientos,ultima

def grupos(avisos):
    g=defaultdict(list)
    for a in avisos:g[(a.equipo_codigo,a.modo)].append(a)
    return g

def prioridad(eventos):
    eventos=sorted(eventos,key=lambda x:x.fecha)
    if not eventos:return 0
    tp=sum(e.tp_min for e in eventos)
    ultimos30=sum((eventos[-1].fecha-e.fecha).days<=30 for e in eventos)
    intervalo=(eventos[-1].fecha-eventos[0].fecha).days if len(eventos)>1 else 365
    return round(min(tp/30,40)+min(len(eventos)*5,25)+min(ultimos30*6,24)+(11 if len(eventos)>1 and intervalo<=7 else 0),1)

def plazo_sugerido(eventos):
    fechas=sorted({e.fecha for e in eventos})
    intervalos=[(b-a).days for a,b in zip(fechas,fechas[1:]) if (b-a).days>0]
    if len(intervalos)>=2:
        base=sorted(intervalos)[len(intervalos)//2]
        return min(365,max(14,round(base*3))),'media',f'3 veces la mediana histórica entre eventos ({base} días). Requiere exposición representativa.'
    if len(intervalos)==1:
        return min(365,max(30,intervalos[0]*3)),'baja','Solo un intervalo conocido; estimación conservadora, no demuestra efectividad por sí sola.'
    return 180,'muy baja','Falla única o sin antecedentes: plazo provisional de 180 días; requiere evidencia del control y exposición operativa.'

def adfs_vinculados(aviso,adfs):
    return [a for a in adfs if str(aviso.aviso) in re.split(r'[^0-9]+',str(a.aviso_sap or '')) or (str(a.numero_equipo or '').strip()==aviso.equipo_codigo and str(a.numero_equipo or '').strip())]

def estado_efectividad(adf,avisos,seguimiento,ultima):
    import json
    try:planes=json.loads(adf.plan_prevencion or '[]')
    except Exception:planes=[]
    if not isinstance(planes,list) or not planes:return 'Planes sin completar','No existen planes estructurados'
    if any(not isinstance(p,dict) or p.get('estado_ejecucion')!='Ejecutado verificado' for p in planes):return 'Planes pendientes','Todos los planes deben estar ejecutados y verificados'
    if not seguimiento or not seguimiento.inicio:return 'Pendiente de seguimiento','Falta fecha de ejecución de la última acción causal'
    fecha_fin=seguimiento.inicio+dt.timedelta(days=seguimiento.plazo_dias)
    if ultima is None or ultima<fecha_fin:return 'En observación','Historial SAP insuficiente para cerrar el período'
    posteriores=[a for a in avisos if a.fecha>seguimiento.inicio and a.fecha<=ultima]
    if posteriores:return 'Posible reincidencia',f'{len(posteriores)} aviso(s) posteriores por revisar; no implica misma causa'
    if not (seguimiento.evidencia_validada or '').strip():return 'Evidencia insuficiente','Plazo cumplido, pero falta evidencia técnica verificada de exposición y control'
    if seguimiento.confianza in ('baja','muy baja'):return 'Evidencia insuficiente','Historial escaso: revisar evidencia y exposición; no se valida automáticamente'
    return 'Efectividad validada','Plazo cumplido, planes verificados y sin aviso similar en los datos disponibles'
