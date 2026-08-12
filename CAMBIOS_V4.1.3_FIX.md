# RootMine v4.1.3 FIX

- Mantiene borradores persistentes de v4.1.3.
- Conexión Supabase más estable para Streamlit.
- SQLAlchemy usa `NullPool` porque Supabase Session Pooler ya administra conexiones.
- SSL obligatorio (`sslmode=require`).
- Timeout de conexión de 10 segundos.
- Evita reutilizar conexiones cerradas por Supabase entre reruns.
