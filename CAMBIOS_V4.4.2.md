# RootMine v4.4.2 — Reincidencias y analítica de modos de falla

## Reincidencias
- Detecta posibles reincidencias solo dentro del mismo activo.
- Si mismo equipo + modo de falla son suficientemente parecidos, permite seleccionar ADF anteriores como antecedente.
- Las conclusiones/causas anteriores pueden entregarse a GearBot como referencia.
- El nuevo ADF sigue siendo independiente.
- Los planes anteriores NO se copian.
- GearBot recibe instrucción explícita para evaluar si los planes anteriores fueron insuficientes, no se ejecutaron o requieren una acción diferente.

## Indicadores — Modos de falla
- Nuevo bloque de modos de falla basado exclusivamente en ADF registrados en RootMine.
- Excluye borradores.
- Vista global de modos de falla.
- Filtro por equipo.
- Opción para mostrar solo modos repetidos.
- Cantidad de ADF por modo de falla.
- Causas raíz registradas por modo.
- Tiempo perdido asociado.
- Historial causal por equipo con sus planes registrados.
- Descarga de reporte CSV del filtro actual.

## Compatibilidad
- Mantiene análisis vivo, navegación dinámica, planes obligatorios, sesión persistente, Supabase y trazabilidad.
- Sin cambio de esquema de base de datos.
