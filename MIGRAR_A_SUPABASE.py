"""Migra la base SQLite local de RootMine y el maestro JSON a PostgreSQL/Supabase.

Uso:
  1) Configura DATABASE_URL en .streamlit/secrets.toml o como variable de entorno.
  2) Ejecuta: python MIGRAR_A_SUPABASE.py

El script NO borra la base local.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from database.modelos import Base, ADF, ValidacionADF, NotificacionInterna, LlaveAcceso, UsuarioRootMine


def secret_local(nombre: str) -> str:
    valor = os.getenv(nombre, "").strip()
    if valor:
        return valor
    p = Path(".streamlit/secrets.toml")
    if p.exists():
        try:
            import tomllib
            return str(tomllib.loads(p.read_text(encoding="utf-8")).get(nombre, "") or "").strip()
        except Exception:
            pass
    return ""

url = secret_local("DATABASE_URL")
if url.startswith("postgres://"):
    url = "postgresql://" + url[len("postgres://"):]
if not url:
    raise SystemExit("Falta DATABASE_URL. Configúrala antes de migrar.")

local = create_engine("sqlite:///data/adf_ia.db", connect_args={"check_same_thread": False})
cloud = create_engine(url, pool_pre_ping=True)
Base.metadata.create_all(cloud)

MODELOS = [ADF, ValidacionADF, NotificacionInterna, LlaveAcceso]

with Session(local) as origen, Session(cloud) as destino:
    for modelo in MODELOS:
        try:
            filas = list(origen.scalars(select(modelo)).all())
        except Exception as exc:
            print(f"{modelo.__tablename__}: no disponible en SQLite ({exc})")
            continue
        copiados = 0
        for fila in filas:
            datos = {c.name: getattr(fila, c.name) for c in modelo.__table__.columns}
            pk = datos.get("id")
            existente = destino.get(modelo, pk) if pk is not None else None
            if existente:
                continue
            destino.add(modelo(**datos))
            copiados += 1
        destino.commit()
        print(f"{modelo.__tablename__}: {copiados} registro(s) migrado(s)")

    # Usuarios: fuente inicial JSON. Si ya existen en nube no los duplica.
    p = Path("data/usuarios_adf.json")
    semillas = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    creados = 0
    for u in semillas:
        correo = (u.get("correo") or "").strip().lower()
        if not correo:
            continue
        if destino.scalar(select(UsuarioRootMine).where(UsuarioRootMine.correo == correo)):
            continue
        resp = u.get("responsable_de") or []
        if isinstance(resp, str):
            resp = [x.strip() for x in resp.replace(";", ",").split(",") if x.strip()]
        destino.add(UsuarioRootMine(
            rut=u.get("rut", ""), nombre=u.get("nombre", ""), correo=correo, area=u.get("area", ""),
            job_code=u.get("job_code", ""), rol=(u.get("rol") or "tecnico").lower(),
            centro=str(u.get("centro") or ""), planta=u.get("planta", ""), activo=bool(u.get("activo", True)),
            responsable_de=json.dumps(resp, ensure_ascii=False),
        ))
        creados += 1
    destino.commit()
    print(f"usuario_rootmine: {creados} usuario(s) migrado(s)")

print("Migración terminada. La base SQLite local no fue modificada.")
