from pathlib import Path

from sqlalchemy import create_engine

DB_PATH = Path("data/adf_ia.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


def crear_tablas() -> None:
    from database.modelos import Base
    Base.metadata.create_all(engine)
