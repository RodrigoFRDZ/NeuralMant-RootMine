# RootMine v4.2.1 — Seguridad de sesión

- El token de autenticación ya no se guarda ni se lee desde la URL.
- Compartir/copiar el enlace de RootMine no comparte la sesión del usuario.
- Los parámetros `rm_session` de versiones anteriores se eliminan automáticamente si aparecen.
- Botón visible `🚪 Cerrar sesión` en la barra lateral.
- Al cerrar sesión:
  - se invalida el token persistente en Supabase;
  - se limpia el usuario y estado sensible de Streamlit;
  - se vuelve al login.
- Si Supabase no responde al cerrar sesión, RootMine igualmente limpia la sesión local.
- Mantiene timeout de 30 minutos sin actividad.
- No modifica el esquema de Supabase ni los ADF almacenados.
