# RootMine v4.1.9 — Optimización de rendimiento

- Reutiliza un pool pequeño de conexiones Supabase.
- Verifica tablas y maestro de usuarios una sola vez por proceso.
- Sesión persistente: renueva en Supabase como máximo cada 5 min, manteniendo 30 min de inactividad.
- Dashboard usa consultas agregadas y no descarga PDFs/respaldos.
- Borradores/correcciones cargan solo columnas visibles.
- Pendientes usa COUNT().
- Cache corto: dashboard 20 s, GearBot 30 s, almacenamiento 90 s y notificaciones 20 s.
- Botón de actualización manual para Capacidad RootMine.
- No cambia el esquema ni la base Supabase.

- Corrección: `Análisis recientes` ahora usa una consulta liviana propia y ya no depende de la variable `registros`.

- FIX3: `Análisis recientes` carga explícitamente `planta` y todos los campos usados por la tarjeta, evitando `DetachedInstanceError` tras cerrar la sesión SQLAlchemy.

- FIX4: caché de notificaciones convierte correctamente objetos `NotificacionInterna` a diccionarios antes de mostrarlos.
