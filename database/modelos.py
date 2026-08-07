from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ADF(Base):
    __tablename__ = "adf"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    creado_por: Mapped[str] = mapped_column(String(150))
    estado: Mapped[str] = mapped_column(String(50), default="Borrador")
    etapa: Mapped[str] = mapped_column(String(100), default="Redacción IA")
    area: Mapped[str] = mapped_column(String(100))
    equipo: Mapped[str] = mapped_column(String(200))
    aviso_sap: Mapped[str] = mapped_column(String(30), default="")
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
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
    )
