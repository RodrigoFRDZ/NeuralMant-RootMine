# RootMine v4.1 Cloud — Supabase PostgreSQL

## Objetivo
Los ADF, usuarios, llaves, aprobaciones, notificaciones y planes dejan de depender del disco temporal de Streamlit.

## 1. Crear proyecto Supabase
1. Crea un proyecto gratuito en Supabase.
2. Guarda la contraseña de la base de datos.
3. En el Dashboard pulsa **Connect**.
4. Selecciona **Session pooler** (puerto 5432). Es la alternativa compatible con IPv4 para un backend persistente.
5. Copia la cadena de conexión PostgreSQL.

## 2. Desarrollo local
En `.streamlit/secrets.toml` agrega:

```toml
GEMINI_API_KEY = "..."
DATABASE_URL = "postgresql://..."
```

No subas `secrets.toml` a GitHub.

## 3. Streamlit Community Cloud
En **App > Settings > Secrets** agrega las mismas dos variables:

```toml
GEMINI_API_KEY = "..."
DATABASE_URL = "postgresql://..."
```

Al reiniciar, RootMine crea sus tablas automáticamente. Si la tabla de usuarios está vacía, importa una sola vez los usuarios iniciales incluidos en `data/usuarios_adf.json`. Desde ese momento, los cambios del menú Administración se guardan en PostgreSQL.

## 4. Migrar datos locales existentes (opcional)
Antes de publicar la v4.1, ejecuta localmente:

```powershell
python MIGRAR_A_SUPABASE.py
```

Esto copia los ADF/validaciones/notificaciones/llaves disponibles en `data/adf_ia.db` y los usuarios iniciales. No borra SQLite.

## 5. Roles técnicos nuevos
- Programador de Mantenimiento
- Ingeniero de Confiabilidad
- Ingeniero de Procesos

Tienen el mismo nivel funcional que Técnico/Senior: crean y trabajan ADF, pero no validan, no liberan y no administran cuentas.

## 6. Administrador
La única cuenta administradora es `rfernandezc@agrosuper.com` (Ingeniero de Mantenimiento).
