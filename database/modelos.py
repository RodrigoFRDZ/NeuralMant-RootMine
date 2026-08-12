from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ADF(Base):
    __tablename__ = "adf"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    creado_por: Mapped[str] = mapped_column(String(150))
    creado_por_email: Mapped[str] = mapped_column(String(180), default="")
    estado: Mapped[str] = mapped_column(String(50), default="Borrador")
    etapa: Mapped[str] = mapped_column(String(100), default="Redacción IA")
    centro: Mapped[str] = mapped_column(String(120), default="")
    planta: Mapped[str] = mapped_column(String(120), default="")
    area: Mapped[str] = mapped_column(String(100))
    numero_equipo: Mapped[str] = mapped_column(String(80), default="")
    equipo: Mapped[str] = mapped_column(String(200))
    aviso_sap: Mapped[str] = mapped_column(String(30), default="")
    tiempo_perdido_h: Mapped[float] = mapped_column(Float, default=0.0)
    relato_original: Mapped[str] = mapped_column(Text)
    analisis_ia: Mapped[str] = mapped_column(Text, default="")
    efecto: Mapped[str] = mapped_column(Text, default="")
    investigacion_web: Mapped[str] = mapped_column(Text, default="")
    fuentes_web: Mapped[str] = mapped_column(Text, default="")
    ishikawa: Mapped[str] = mapped_column(Text, default="")
    causas_priorizadas: Mapped[str] = mapped_column(Text, default="")
    cadenas_causales: Mapped[str] = mapped_column(Text, default="")
    conclusion: Mapped[str] = mapped_column(Text, default="")
    plan_prevencion: Mapped[str] = mapped_column(Text, default="")
    leccion_aprendida: Mapped[str] = mapped_column(Text, default="")
    pdf_archivo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    borrador_paso: Mapped[int] = mapped_column(Integer, default=1)
    borrador_json: Mapped[str] = mapped_column(Text, default="")

    supervisor_nombre: Mapped[str] = mapped_column(String(150), default="")
    supervisor_email: Mapped[str] = mapped_column(String(180), default="")
    jefe_nombre: Mapped[str] = mapped_column(String(150), default="")
    jefe_email: Mapped[str] = mapped_column(String(180), default="")
    comentario_validacion: Mapped[str] = mapped_column(Text, default="")
    ultima_validacion_por: Mapped[str] = mapped_column(String(180), default="")
    fecha_envio_validacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fecha_aprobacion_supervisor: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fecha_aprobacion_jefe: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class ValidacionADF(Base):
    __tablename__ = "validacion_adf"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    adf_id: Mapped[int] = mapped_column(Integer, index=True)
    etapa: Mapped[str] = mapped_column(String(50))
    accion: Mapped[str] = mapped_column(String(50))
    usuario_nombre: Mapped[str] = mapped_column(String(150))
    usuario_email: Mapped[str] = mapped_column(String(180))
    comentario: Mapped[str] = mapped_column(Text, default="")
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class NotificacionInterna(Base):
    __tablename__ = "notificacion_interna"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    destinatario_email: Mapped[str] = mapped_column(String(180), index=True)
    adf_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    tipo: Mapped[str] = mapped_column(String(60), default="info")
    titulo: Mapped[str] = mapped_column(String(200))
    mensaje: Mapped[str] = mapped_column(Text, default="")
    leida: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class LlaveAcceso(Base):
    __tablename__ = "llave_acceso"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    correo: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    salt_b64: Mapped[str] = mapped_column(String(120))
    hash_b64: Mapped[str] = mapped_column(String(180))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class UsuarioRootMine(Base):
    __tablename__ = "usuario_rootmine"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rut: Mapped[str] = mapped_column(String(40), default="")
    nombre: Mapped[str] = mapped_column(String(180))
    correo: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    area: Mapped[str] = mapped_column(String(120), default="")
    job_code: Mapped[str] = mapped_column(String(180), default="")
    rol: Mapped[str] = mapped_column(String(80), default="tecnico", index=True)
    centro: Mapped[str] = mapped_column(String(40), default="", index=True)
    planta: Mapped[str] = mapped_column(String(120), default="")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    es_admin: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    responsable_de: Mapped[str] = mapped_column(Text, default="[]")
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class SesionRootMine(Base):
    __tablename__ = "sesion_rootmine"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    correo: Mapped[str] = mapped_column(String(180), index=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    ultima_actividad: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


class UsoIA(Base):
    __tablename__ = "uso_ia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    modelo: Mapped[str] = mapped_column(String(120), default="")
    operacion: Mapped[str] = mapped_column(String(120), default="")
    resultado: Mapped[str] = mapped_column(String(40), default="ok", index=True)
    usuario_email: Mapped[str] = mapped_column(String(180), default="", index=True)
