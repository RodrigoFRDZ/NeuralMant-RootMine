from pathlib import Path

from sqlalchemy import create_engine, inspect, text

DB_PATH = Path("data/adf_ia.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


def crear_tablas() -> None:
    from database.modelos import Base
    Base.metadata.create_all(engine)

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
    }
    with engine.begin() as conexion:
        for nombre, definicion in nuevas_columnas.items():
            if nombre not in columnas:
                conexion.execute(text(f"ALTER TABLE adf ADD COLUMN {nombre} {definicion}"))
