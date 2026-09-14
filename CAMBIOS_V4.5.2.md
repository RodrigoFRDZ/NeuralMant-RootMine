# RootMine v4.5.2 · Línea causal reactiva

## Cambio principal
Cuando el investigador modifica las causas probables/priorizadas, RootMine considera obsoletos los 5 Porqués y planes de la versión causal anterior y reconstruye el análisis con GearBot.

## Comportamiento
- Detecta cambios reales en la selección de causas priorizadas.
- Antes de invalidar la cadena anterior, rescata los aportes manuales que difieren de la propuesta IA (respuestas, justificaciones, evidencias y causa raíz anotada).
- Esos aportes se conservan como antecedentes técnicos de edición, no como conclusiones vigentes.
- Los 5 Porqués anteriores se eliminan del análisis actual y se reconstruyen desde cero para las nuevas causas.
- GearBot puede reutilizar un aporte del técnico solo si sigue siendo coherente con los hechos y la nueva línea causal; no fuerza ni copia contenido irrelevante.
- Los planes anteriores se invalidan y se vuelven a generar en función de la nueva causa raíz.
- El informe queda marcado para actualización con la lógica de análisis vivo.
- Se limpian widgets de 5 Porqués y planes para evitar que Streamlit reponga valores antiguos en pantalla.

## Persistencia
Los antecedentes técnicos se guardan dentro del snapshot del borrador (`borrador_json`), sin cambios de esquema en Supabase. Se conservan hasta las últimas 5 revisiones para no aumentar indefinidamente el contexto enviado a IA.

## Compatibilidad
No requiere migración de base de datos. Mantiene el flujo de corrección tras rechazo de Jefatura incorporado en v4.5.1.
