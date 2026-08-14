# RootMine v4.2.0 — Ishikawa dinámico, duplicidad y respaldos específicos

## Ishikawa
- Cada M conserva las causas sugeridas por GearBot.
- Se incorpora `＋ Agregar otra causa` para añadir tantas causas observadas como sea necesario.
- Se puede quitar la última causa adicional.
- Las causas agregadas por el equipo investigador pasan al mismo flujo de priorización y 5 Porqués.

## Borradores y recurrencia
- El creador puede eliminar sus propios borradores desde Inicio con confirmación.
- Antes de analizar un nuevo ADF, RootMine avisa si existe un borrador del mismo activo y permite retomarlo.
- Si encuentra ADF históricos con características similares, los muestra antes de iniciar el nuevo análisis.
- Los borradores no se utilizan como conocimiento histórico de fallas similares.

## Planes de prevención y evidencias
- Detecta automáticamente planes de capacitación/charla, POEV y LUP.
- Capacitación/charla requiere:
  - foto de la actividad;
  - registro firmado de capacitación.
- La IA valida que el tema visible en la parte superior del registro sea coherente con el plan y que exista evidencia razonable de firmas/asistencia.
- POEV requiere documento POEV + registro firmado de difusión.
- LUP requiere documento LUP + registro firmado de difusión.
- La IA verifica coherencia entre documento, tema del registro y plan de acción.
- Los respaldos pueden ser imágenes o PDF según corresponda.
- Tamaño máximo por respaldo: 10 MB.

## Compatibilidad
- No cambia el esquema de Supabase.
- Mantiene rendimiento v4.1.9, trazabilidad, sesiones, roles, aprobaciones y datos existentes.
