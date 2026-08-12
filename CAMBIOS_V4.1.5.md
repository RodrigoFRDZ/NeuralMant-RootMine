# RootMine v4.1.5

- La descripción original del equipo se conserva en la base de datos.
- Si la descripción viene completamente en MAYÚSCULAS, la narrativa de IA la normaliza a minúsculas para mejorar la lectura.
- Diagnóstico, Ishikawa, 5 Porqués e informe final usan la descripción normalizada en su contextualización.
- La sesión sobrevive a refrescar/F5 mediante una sesión temporal persistida en Supabase.
- La sesión expira después de 30 minutos sin interacción. Cada interacción válida renueva la actividad.
- Cerrar sesión invalida inmediatamente el token persistente.
- Mantiene borradores persistentes, Administración de ADF y los desplegables de ayuda/evidencia en 5 Porqués.
