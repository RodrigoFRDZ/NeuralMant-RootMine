# RootMine v4.2.4 — Sesión persistente y edición final

## Sesión y seguridad
- La sesión se conserva al refrescar/F5 mediante una cookie segura del navegador.
- El token de sesión NO aparece en la URL.
- Compartir el enlace no comparte la sesión con otra persona.
- Supabase sigue aplicando el límite de 30 minutos sin actividad.
- Al refrescar se recupera:
  - usuario conectado;
  - página en la que estaba;
  - mismo ADF borrador, si estaba trabajando en uno;
  - última etapa guardada del borrador.
- El botón `🚪 Cerrar sesión` queda visible inmediatamente bajo los datos del usuario.
- Cerrar sesión invalida el token en Supabase y elimina las cookies locales.

## Etapa PDF / envío
- Mientras el ADF siga en `Borrador` aparecen:
  - `← Volver y editar`
  - `📨 Enviar a validación`
- `Volver y editar` regresa al Informe y desde ahí se puede seguir retrocediendo a Planes, 5 Porqués, Ishikawa y Contexto/fotos.
- Una vez enviado a validación, la edición queda bloqueada.

## PDF
- `Descargar PDF preliminar` pasa a `📄 Revisar / descargar PDF`.
- Se fuerza fondo azul y texto blanco para mejorar el contraste.

## Compatibilidad
- Mantiene las mejoras de v4.2.3 y versiones anteriores.
- No cambia el esquema de Supabase.
- Los ADF y borradores existentes permanecen intactos.
