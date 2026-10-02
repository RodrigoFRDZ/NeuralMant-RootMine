"""Modelo de materiales compatible con modelos.py de RootMine 4.5.3 y 4.6.0."""
from datetime import datetime
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from database import modelos
from database.modelos import Base

if hasattr(modelos, "SolicitudMaterial"):
    SolicitudMaterial = modelos.SolicitudMaterial
else:
    class SolicitudMaterial(Base):
        __tablename__ = "solicitud_material"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        tipo: Mapped[str] = mapped_column(String(30), index=True)
        solicitante_email: Mapped[str] = mapped_column(String(180), index=True)
        solicitante_nombre: Mapped[str] = mapped_column(String(180))
        centro: Mapped[str] = mapped_column(String(40), index=True)
        area: Mapped[str] = mapped_column(String(120))
        material: Mapped[str] = mapped_column(String(80), index=True)
        estado: Mapped[str] = mapped_column(String(40), default="Borrador", index=True)
        jefe_email: Mapped[str] = mapped_column(String(180), default="")
        analista_email: Mapped[str] = mapped_column(String(180), default="")
        subgerente_email: Mapped[str] = mapped_column(String(180), default="")
        datos_json: Mapped[str] = mapped_column(Text, default="{}")
        historial_json: Mapped[str] = mapped_column(Text, default="[]")
        fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
        fecha_envio: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
        fecha_carga: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
        version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
        __mapper_args__ = {"version_id_col": version}
