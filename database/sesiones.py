from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from database.conexion import engine
from database.modelos import SesionRootMine

MINUTOS_INACTIVIDAD = 30


def _hash_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def crear_sesion(correo: str) -> str:
    correo = (correo or "").strip().lower()
    if not correo:
        raise ValueError("No se puede crear una sesión sin correo.")
    token = secrets.token_urlsafe(32)
    ahora = datetime.now()
    with Session(engine) as session:
        # Limpia sesiones ya vencidas para no acumular registros.
        limite = ahora - timedelta(minutes=MINUTOS_INACTIVIDAD)
        session.execute(delete(SesionRootMine).where(SesionRootMine.ultima_actividad < limite))
        session.add(SesionRootMine(
            token_hash=_hash_token(token),
            correo=correo,
            fecha_creacion=ahora,
            ultima_actividad=ahora,
        ))
        session.commit()
    return token


def validar_y_tocar_sesion(token: str) -> str | None:
    token = (token or "").strip()
    if not token:
        return None
    ahora = datetime.now()
    with Session(engine) as session:
        registro = session.scalar(
            select(SesionRootMine).where(SesionRootMine.token_hash == _hash_token(token))
        )
        if not registro:
            return None
        if ahora - registro.ultima_actividad > timedelta(minutes=MINUTOS_INACTIVIDAD):
            session.delete(registro)
            session.commit()
            return None
        registro.ultima_actividad = ahora
        session.commit()
        return (registro.correo or "").strip().lower()


def cerrar_sesion(token: str) -> None:
    token = (token or "").strip()
    if not token:
        return
    with Session(engine) as session:
        session.execute(delete(SesionRootMine).where(SesionRootMine.token_hash == _hash_token(token)))
        session.commit()
