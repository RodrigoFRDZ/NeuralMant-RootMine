# RootMine v4.0 – Verificación inteligente de respaldos

- Se eliminó la necesidad de transcribir manualmente NOTI, Status de usuario, MOV y gasto para que la IA los compare.
- El módulo admite varias capturas de Orden de Trabajo SAP.
- Se agregaron respaldos separados Foto ANTES y Foto DESPUÉS.
- GearBot lee, cuando son visibles: OT, encabezado/texto breve, Status de usuario, Fecha fin extrema, NOTI, MOV y gasto.
- CTEC + NOTI se considera una señal fuerte de ejecución/notificación, pero además se exige coherencia entre la descripción de la OT y el plan de acción.
- Las fotos ANTES/DESPUÉS se comparan para verificar que el cambio observado corresponda a la acción.
- La IA devuelve: Ejecución respaldada, Evidencia parcial, Evidencia inconsistente o No verificable.
- Solo una Ejecución respaldada con `ejecucion_confirmada=true` cambia el plan a Ejecutado verificado.
- Historial conserva y muestra todos los respaldos y la lectura de IA.
