from sqlalchemy import select
from sqlalchemy.orm import Session

from database.conexion import engine
from database.modelos import NotificacionInterna


def crear_notificacion(destinatario_email: str, titulo: str, mensaje: str, adf_id: int | None = None, tipo: str = "info") -> None:
    email = (destinatario_email or "").strip().lower()
    if not email:
        return
    with Session(engine) as session:
        session.add(NotificacionInterna(
            destinatario_email=email,
            adf_id=adf_id,
            tipo=tipo,
            titulo=titulo,
            mensaje=mensaje,
            leida=False,
        ))
        session.commit()


def listar_notificaciones(email: str, solo_no_leidas: bool = False, limite: int = 12) -> list[NotificacionInterna]:
    email = (email or "").strip().lower()
    if not email:
        return []
    with Session(engine) as session:
        consulta = select(NotificacionInterna).where(NotificacionInterna.destinatario_email == email)
        if solo_no_leidas:
            consulta = consulta.where(NotificacionInterna.leida.is_(False))
        consulta = consulta.order_by(NotificacionInterna.fecha.desc()).limit(limite)
        return list(session.scalars(consulta).all())


def contar_no_leidas(email: str) -> int:
    return len(listar_notificaciones(email, solo_no_leidas=True, limite=1000))


def marcar_leida(notificacion_id: int) -> None:
    with Session(engine) as session:
        n = session.get(NotificacionInterna, notificacion_id)
        if n:
            n.leida = True
            session.commit()


def marcar_todas_leidas(email: str) -> None:
    for n in listar_notificaciones(email, solo_no_leidas=True, limite=1000):
        marcar_leida(n.id)
