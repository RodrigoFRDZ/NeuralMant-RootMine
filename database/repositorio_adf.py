from sqlalchemy import select
from sqlalchemy.orm import Session

from database.conexion import engine
from database.modelos import ADF


def guardar_adf(datos: dict) -> int:
    with Session(engine) as session:
        adf = ADF(**datos)
        session.add(adf)
        session.commit()
        session.refresh(adf)
        return adf.id


def listar_adf() -> list[ADF]:
    with Session(engine) as session:
        consulta = select(ADF).order_by(ADF.fecha_actualizacion.desc())
        return list(session.scalars(consulta).all())
