# RootMine v4.2.2 — Reasignación controlada de borradores

## Administración de borradores
- Nueva pestaña `🔄 Reasignar borradores` exclusiva para cuentas Admin RootMine.
- Un borrador continúa siendo editable únicamente por su responsable actual.
- El Admin puede transferir un borrador a otro usuario activo habilitado para generar ADF.
- La reasignación conserva:
  - mismo ID de ADF;
  - etapa/paso guardado;
  - diagnóstico, Ishikawa, 5 Porqués y planes ya avanzados;
  - fecha e información técnica existente.
- El nuevo responsable verá el borrador en `ADF en progreso` y podrá continuar desde donde quedó.

## Trazabilidad
Cada transferencia registra:
- fecha y hora;
- administrador que realizó la reasignación;
- responsable anterior;
- nuevo responsable;
- motivo/comentario opcional.

El evento queda almacenado en la tabla existente `validacion_adf` como:
`Borrador → Reasignado`, por lo que aparece en la trazabilidad del ADF sin requerir una tabla nueva.

## Notificaciones
- El nuevo responsable recibe una notificación interna informando que el ADF fue reasignado.
- El responsable anterior recibe aviso de la transferencia.

## Compatibilidad
- Mantiene todas las mejoras de v4.2.1: seguridad del enlace y botón Cerrar sesión.
- Mantiene v4.2.0: Ishikawa dinámico, borradores, ADF similares y respaldos para capacitación, POEV y LUP.
- No cambia el esquema de Supabase.
