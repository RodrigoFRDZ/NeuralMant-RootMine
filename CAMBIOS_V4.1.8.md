# RootMine v4.1.8 — Dashboard aprobado + trazabilidad temporal

## Dashboard
- `ADF aprobados` cuenta únicamente registros con estado final `Aprobado`.
- `Equipos analizados` considera solo equipos con ADF aprobado.
- `Áreas cubiertas` considera solo áreas con ADF aprobado.
- Borradores, pendientes, rechazados y devueltos no inflan los indicadores de resultado.

## Historial / trazabilidad
Cada ADF incorpora `🕒 Ver flujo y trazabilidad completa`, mostrando:
- fecha y hora de creación;
- envío a validación;
- aprobaciones y rechazos del Supervisor;
- aprobaciones y rechazos de Jefatura;
- devoluciones al creador;
- reenvíos;
- usuario responsable de cada movimiento;
- comentario/observación de cada validación;
- tiempo transcurrido entre cada evento;
- tiempo total desde creación hasta aprobación final;
- tiempo transcurrido para ADF todavía abiertos.

Los eventos usan la tabla `validacion_adf` ya existente, por lo que no requiere una nueva migración de esquema.
