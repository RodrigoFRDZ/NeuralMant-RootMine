import base64
import hashlib
import hmac
import os
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.conexion import engine
from database.modelos import LlaveAcceso

ROLES_CON_LLAVE = {"supervisor", "jefe", "ingeniero", "subgerente"}
ITERACIONES = 210_000


def requiere_llave(usuario: dict | None) -> bool:
    if not usuario:
        return False
    return (usuario.get("rol") or "").strip().lower() in ROLES_CON_LLAVE


def _derivar(llave: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", llave.encode("utf-8"), salt, ITERACIONES)


def tiene_llave(correo: str) -> bool:
    correo = (correo or "").strip().lower()
    if not correo:
        return False
    with Session(engine) as session:
        return session.scalar(select(LlaveAcceso).where(LlaveAcceso.correo == correo)) is not None


def crear_llave(correo: str, llave: str) -> None:
    correo = (correo or "").strip().lower()
    llave = (llave or "").strip()
    if len(llave) < 6:
        raise ValueError("La llave debe tener al menos 6 caracteres.")
    if tiene_llave(correo):
        raise ValueError("Este usuario ya tiene una llave creada.")

    salt = os.urandom(16)
    digest = _derivar(llave, salt)
    with Session(engine) as session:
        session.add(
            LlaveAcceso(
                correo=correo,
                salt_b64=base64.b64encode(salt).decode("ascii"),
                hash_b64=base64.b64encode(digest).decode("ascii"),
                fecha_creacion=datetime.now(),
            )
        )
        session.commit()


def validar_llave(correo: str, llave: str) -> bool:
    correo = (correo or "").strip().lower()
    with Session(engine) as session:
        registro = session.scalar(select(LlaveAcceso).where(LlaveAcceso.correo == correo))
        if not registro:
            return False
        salt = base64.b64decode(registro.salt_b64.encode("ascii"))
        esperado = base64.b64decode(registro.hash_b64.encode("ascii"))
        obtenido = _derivar((llave or "").strip(), salt)
        return hmac.compare_digest(esperado, obtenido)


def eliminar_llave(correo: str) -> bool:
    correo = (correo or "").strip().lower()
    with Session(engine) as session:
        registro = session.scalar(select(LlaveAcceso).where(LlaveAcceso.correo == correo))
        if not registro:
            return False
        session.delete(registro)
        session.commit()
        return True
