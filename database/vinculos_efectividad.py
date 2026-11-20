"""Vínculos SAP-ADF auditables. No modifica la tabla ADF ni los avisos históricos."""
from datetime import datetime
from sqlalchemy import Integer, String, DateTime, Text, ForeignKey, select
from sqlalchemy.orm import Mapped, mapped_column, Session
from database.modelos import Base, ADF
from database.conexion import engine

class VinculoEfectividad(Base):
    __tablename__ = 'historial_vinculo_efectividad'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    adf_id: Mapped[int] = mapped_column(Integer, index=True)
    aviso: Mapped[str] = mapped_column(String(40), index=True)
    tipo: Mapped[str] = mapped_column(String(30))  # origen, reincidencia
    confirmado_por: Mapped[str] = mapped_column(String(180), default='')
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    comentario: Mapped[str] = mapped_column(Text, default='')


def preparar():
    Base.metadata.create_all(engine, tables=[VinculoEfectividad.__table__])


def obtener_vinculos():
    preparar()
    with Session(engine) as db:
        return [(v.adf_id, v.aviso, v.tipo, v.confirmado_por, v.comentario)
                for v in db.scalars(select(VinculoEfectividad)).all()]


def confirmar_vinculo(adf_id, aviso, tipo, usuario, comentario=''):
    if tipo not in ('origen', 'reincidencia'):
        raise ValueError('Tipo de vínculo inválido')
    if not usuario or not (usuario.get('es_admin') or usuario.get('rol') in ('jefe','subgerente','supervisor','ingeniero','ingeniero_confiabilidad')):
        raise PermissionError('Usuario no autorizado')
    correo = str(usuario.get('correo') or usuario.get('email') or usuario.get('nombre') or '').strip()
    if not correo:
        raise PermissionError('Identidad de usuario requerida')
    preparar()
    with Session(engine) as db:
        if db.get(ADF, int(adf_id)) is None:
            raise ValueError('ADF inexistente')
        existe = db.scalar(select(VinculoEfectividad).where(
            VinculoEfectividad.adf_id == int(adf_id),
            VinculoEfectividad.aviso == str(aviso), VinculoEfectividad.tipo == tipo))
        if existe:
            return False
        db.add(VinculoEfectividad(adf_id=int(adf_id), aviso=str(aviso), tipo=tipo,
                                 confirmado_por=correo, comentario=str(comentario)))
        db.commit()
    return True


def reabrir_adf_por_reincidencia(adf_id, usuario):
    """Reapertura explícita, conserva los planes, PDF y vínculos anteriores."""
    from database.modelos import ValidacionADF
    if not usuario or not (usuario.get('es_admin') or usuario.get('rol') in ('jefe','subgerente','supervisor','ingeniero','ingeniero_confiabilidad')):
        raise PermissionError('Usuario no autorizado')
    correo = str(usuario.get('correo') or usuario.get('email') or '').strip()
    if not correo:
        raise PermissionError('Se requiere un correo de usuario identificado')
    with Session(engine) as db:
        adf = db.get(ADF, int(adf_id))
        if adf is None:
            raise ValueError('ADF no encontrado')
        vinculos = db.scalars(select(VinculoEfectividad).where(
            VinculoEfectividad.adf_id == int(adf_id),
            VinculoEfectividad.tipo == 'reincidencia')).all()
        if not vinculos:
            raise ValueError('Primero debes confirmar y vincular una reincidencia')
        if adf.estado in ('Borrador', 'Requiere corrección') and adf.etapa == 'Reapertura por reincidencia':
            return False
        estado_previo = adf.estado
        adf.estado = 'Requiere corrección'
        adf.etapa = 'Reapertura por reincidencia'
        db.add(ValidacionADF(adf_id=int(adf_id), etapa='Reapertura por reincidencia',
                             accion='Reabrir', usuario_nombre=str(usuario.get('nombre') or correo),
                             usuario_email=correo,
                             comentario=f'Estado anterior: {estado_previo}. Avisos asociados: {", ".join(v.aviso for v in vinculos)}'))
        db.commit()
        return True
