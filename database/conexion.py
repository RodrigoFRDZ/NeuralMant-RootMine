from __future__ import annotations

import os
from pathlib import Path

import tomllib
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

DB_PATH = Path("data/adf_ia.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _secret(nombre: str, defecto: str = "") -> str:
    # Streamlit Community Cloud expone los secretos de nivel raíz como variables
    # del entorno; para desarrollo local también leemos secrets.toml directamente.
    valor = str(os.getenv(nombre, "") or "").strip()
    if valor:
        return valor
    ruta = Path(".streamlit/secrets.toml")
    if ruta.exists():
        try:
            datos = tomllib.loads(ruta.read_text(encoding="utf-8"))
            valor = str(datos.get(nombre, "") or "").strip()
            if valor:
                return valor
        except Exception:
            pass
    try:
        import streamlit as st
        return str(st.secrets.get(nombre, defecto) or defecto).strip()
    except Exception:
        return str(defecto or "").strip()


def _database_url() -> str:
    url = _secret("DATABASE_URL")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def usando_nube() -> bool:
    return bool(_database_url())


def descripcion_backend() -> str:
    return "Supabase PostgreSQL" if usando_nube() else "SQLite local"


def _crear_engine() -> Engine:
    url = _database_url()
    if url:
        # Reutiliza un pequeño pool local para evitar renegociar TCP/SSL en cada consulta.
        return create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=3,
            max_overflow=2,
            pool_timeout=10,
            connect_args={
                "connect_timeout": 10,
                "sslmode": "require",
                "application_name": "rootmine",
            },
        )
    return create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False},
    )


engine = _crear_engine()


def crear_tablas() -> None:
    from database.modelos import Base
    Base.metadata.create_all(engine)

    inspector = inspect(engine)

    # v4.1.1: permiso administrativo explícito, independiente del cargo.
    if "usuario_rootmine" in inspector.get_table_names():
        cols_usuario = {c["name"] for c in inspector.get_columns("usuario_rootmine")}
        if "es_admin" not in cols_usuario:
            with engine.begin() as conexion:
                if engine.dialect.name == "postgresql":
                    conexion.execute(text("ALTER TABLE usuario_rootmine ADD COLUMN es_admin BOOLEAN NOT NULL DEFAULT FALSE"))
                else:
                    conexion.execute(text("ALTER TABLE usuario_rootmine ADD COLUMN es_admin BOOLEAN NOT NULL DEFAULT 0"))
        # Garantiza que la cuenta maestra inicial no pierda acceso al migrar.
        with engine.begin() as conexion:
            conexion.execute(text("UPDATE usuario_rootmine SET es_admin = TRUE WHERE lower(correo) = 'rfernandezc@agrosuper.com'"))

    # v4.1.3: columnas para borradores persistentes.
    if "adf" in inspector.get_table_names():
        cols_adf = {c["name"] for c in inspector.get_columns("adf")}
        with engine.begin() as conexion:
            if "borrador_paso" not in cols_adf:
                conexion.execute(text("ALTER TABLE adf ADD COLUMN borrador_paso INTEGER DEFAULT 1"))
            if "borrador_json" not in cols_adf:
                conexion.execute(text("ALTER TABLE adf ADD COLUMN borrador_json TEXT DEFAULT ''"))

    # El resto de ALTER históricos solo aplica al SQLite local.
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    if "adf" not in inspector.get_table_names():
        return

    columnas = {columna["name"] for columna in inspector.get_columns("adf")}
    nuevas_columnas = {
        "centro": "VARCHAR(120) DEFAULT ''",
        "planta": "VARCHAR(120) DEFAULT ''",
        "numero_equipo": "VARCHAR(80) DEFAULT ''",
        "creado_por_email": "VARCHAR(180) DEFAULT ''",
        "supervisor_nombre": "VARCHAR(150) DEFAULT ''",
        "supervisor_email": "VARCHAR(180) DEFAULT ''",
        "jefe_nombre": "VARCHAR(150) DEFAULT ''",
        "jefe_email": "VARCHAR(180) DEFAULT ''",
        "comentario_validacion": "TEXT DEFAULT ''",
        "ultima_validacion_por": "VARCHAR(180) DEFAULT ''",
        "fecha_envio_validacion": "DATETIME",
        "fecha_aprobacion_supervisor": "DATETIME",
        "fecha_aprobacion_jefe": "DATETIME",
        "pdf_archivo": "BLOB",
        "tiempo_perdido_h": "FLOAT DEFAULT 0",
        "borrador_paso": "INTEGER DEFAULT 1",
        "borrador_json": "TEXT DEFAULT ''",
    }
    with engine.begin() as conexion:
        for nombre, definicion in nuevas_columnas.items():
            if nombre not in columnas:
                conexion.execute(text(f"ALTER TABLE adf ADD COLUMN {nombre} {definicion}"))
