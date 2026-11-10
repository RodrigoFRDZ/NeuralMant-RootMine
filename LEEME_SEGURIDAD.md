# NeuralMant — paquete de seguridad (candidato de pruebas, NO publicado)

## Archivos
Copiar `neuralmant_ui.py` a la raíz del proyecto y los archivos de `database/` a su carpeta homónima. `app.py` se incluye como referencia, sin modificaciones.

## Cambios
- Elimina el `CookieManager` global y no reutiliza cookies de autenticación. El token se mantiene solo en `st.session_state` por conexión WebSocket; F5 requiere nuevo inicio de sesión.
- Obliga a introducir contraseña a todas las cuentas, sin acceso solo con correo.
- Autoactivación provisional solo para roles técnicos sin permisos administrativos (riesgo conocido de suplantación antes de la activación).
- Cuentas privilegiadas sin contraseña: bloqueadas hasta activación verificada por un procedimiento externo. **Este paquete NO implementa aún la interfaz de activación privilegiada**.
- Verifica token y usuario activo en cada rerun; expira a los 30 min de inactividad y 12 h de duración absoluta.
- Limita a cinco intentos fallidos por 15 minutos en memoria del proceso. **No sirve como limitador distribuido** en varias instancias; sustituir por mecanismo compartido antes de producción.
- Evita reasignación automática de privilegios a un correo específico en inicialización.
- Protección adicional de la ruta de administración.

## Requisitos antes de publicar
1. Respaldar PostgreSQL; probar con copia de la base en entorno de staging.
2. Revisar todos los módulos y endpoints (incluido `campo_enlace`) y las políticas RLS: el paquete no audita esas rutas.
3. Revisar el módulo de administración que puede eliminar/restablecer claves; asegurar verificación de identidad antes de cualquier cambio de clave privilegiada.
4. Crear procedimiento de activación verificada para cuentas privilegiadas que aún no tengan contraseña.
5. Invalidar las sesiones antiguas en ventana de despliegue mediante SQL `DELETE FROM sesion_rootmine;` **solo después de respaldo y aprobación**. No se ejecuta automáticamente.
6. Probar con dos navegadores/equipos, logout, F5, roles, 30 min de inactividad, bloqueo, desactivación y rotación de contraseñas.
7. Confirmar que los permisos del backend se validan por operación, no solo por navegación. Con `DATABASE_URL` servidor, RLS por sí sola puede no aislar usuarios.

## Riesgos residuales
- El primer usuario que conozca un correo técnico todavía sin contraseña podría apropiarse de esa cuenta. Es una concesión provisional solicitada, no autenticación de identidad segura.
- No hay envío automático de correos, recuperación autoservicio ni activación privilegiada en este paquete.
- `extra_streamlit_components` ya no es necesario para `neuralmant_ui.py`, pero otros módulos podrían seguir usándolo.
- El límite de intentos es por proceso y se pierde al reiniciar.
- Las pruebas de integración y dos dispositivos reales no se han ejecutado en este entorno.

## Rollback
Restaurar archivos anteriores desde Git y revertir despliegue; no hay migraciones destructivas de tablas en este paquete.
