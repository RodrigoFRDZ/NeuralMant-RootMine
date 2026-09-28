# RootMine v4.5.3

## Corrección de despliegue Streamlit Cloud

- Se actualiza el driver PostgreSQL requerido por SQLAlchemy de `psycopg2-binary` a `psycopg[binary]` (psycopg 3).
- Corrige el `ModuleNotFoundError` observado al iniciar la aplicación en Streamlit Cloud cuando la conexión usa el dialecto `postgresql+psycopg`.
- Mantiene todas las mejoras de v4.5.2: línea causal reactiva, regeneración de 5 Porqués y planes, y corrección tras devolución de Jefatura.
- No requiere cambios de esquema en Supabase ni cambios en `DATABASE_URL`.
