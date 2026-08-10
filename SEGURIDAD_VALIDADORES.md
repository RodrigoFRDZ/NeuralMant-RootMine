# Seguridad de validadores · RootMine v4.0

## Llave de acceso
Los perfiles Supervisor, Jefe, Ingeniero y Subgerente requieren una llave personal además del correo registrado.

- En el primer ingreso el usuario crea su propia llave (mínimo 6 caracteres).
- La llave nunca se guarda en texto visible: se almacena mediante PBKDF2-HMAC-SHA256 con salt individual.
- Técnicos y Senior no requieren llave porque no participan en la liberación del ADF.
- Si un validador olvida la llave, el perfil Ingeniero puede ir a `🔐 Administración`, seleccionar al usuario y eliminar su llave. En el siguiente acceso el usuario creará una nueva.

## Liberación de ADF
Los perfiles autorizados disponen de `✅ Validaciones`.

1. Abrir el ADF con `Abrir validación`.
2. Revisar fenómeno, conclusión, equipo y trazabilidad.
3. Seleccionar `APROBAR Y LIBERAR` o `RECHAZAR`.
4. El rechazo exige comentario.
5. El Ingeniero puede intervenir como reemplazo y la trazabilidad registra esa condición.

> Esta llave agrega una capa de seguridad dentro de RootMine, pero el correo de ingreso sigue siendo una identificación interna y no equivale a autenticación corporativa SSO.
