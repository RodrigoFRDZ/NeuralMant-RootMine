# RootMine v4.2.5 — FIX navegación y botones

## Corrección crítica
La v4.2.4 restauraba página y borrador desde las cookies en cada rerun de Streamlit.
Eso podía sobrescribir inmediatamente la acción de un botón y dar la impresión de que
el botón cargaba pero no hacía nada.

## Nuevo comportamiento
- Las cookies de página/borrador se leen UNA sola vez después de reconstruir la sesión por F5.
- Después de esa restauración, los botones y la navegación gobiernan normalmente el estado.
- Las cookies solo se escriben cuando realmente cambia la página o el borrador activo.
- No se consulta el CookieManager repetidamente en cada rerun.
- Inicio de sesión nuevo arranca en Dashboard y no recupera una pantalla antigua.
- F5 conserva sesión, página y borrador cuando corresponde.
- El token sigue sin aparecer en la URL.
- Cerrar sesión sigue invalidando Supabase y limpiando cookies.

## Mantiene
- Volver y editar antes de enviar a validación.
- Botón PDF con alto contraste.
- Reasignación y continuación de borradores.
- Ishikawa dinámico y respaldos especiales.
- Supabase sin cambios de esquema.
