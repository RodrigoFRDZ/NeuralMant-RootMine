# RootMine v4.5.1 · Corrección directa tras rechazo de Jefatura

## Problema corregido
Cuando Jefatura rechazaba un ADF, el análisis volvía al Supervisor como `Devuelto por Jefatura`, pero el Supervisor solo podía devolverlo al creador o reenviarlo sin editar. Si el mismo Supervisor había creado el ADF, quedaba sin una ruta lógica para corregirlo.

## Nuevo flujo
- Jefatura rechaza → el ADF vuelve al Supervisor.
- El Supervisor dispone de **✏️ CORREGIR ADF**.
- Si Supervisor y creador son la misma persona, RootMine ya no muestra la acción redundante de devolverse el ADF a sí mismo.
- Si el creador es otra persona, el Supervisor puede elegir entre devolver al creador o corregir directamente.
- La corrección abre el **mismo ADF**, conserva su ID, creador, observación de Jefatura y trazabilidad.
- Desde PDF / envío se puede volver a cualquier etapa anterior para corregir.
- Después de guardar la corrección, el ADF se **reenvía directamente a Jefatura**, sin una segunda autoaprobación del Supervisor.
- Se registra el movimiento en la trazabilidad y Jefatura recibe la notificación correspondiente.

## Compatibilidad
- Sin cambios de esquema de base de datos.
- Compatible con ADF existentes que ya estén en estado `Devuelto por Jefatura`.
- Mantiene la lógica de guardado seguro e IA reactiva de v4.5.0.
