# RootMine v4.5.0 — Guardado seguro + IA reactiva + navegación libre hacia atrás

## 1. Guardado seguro al retroceder
- Las ediciones manuales dejan de perderse al volver a una etapa anterior.
- Antes de viajar, RootMine guarda la versión que está viendo el investigador.
- Ishikawa, priorización, 5 Porqués, planes e informe conservan sus modificaciones humanas.
- Los planes editados vuelven a cargarse desde la versión validada, no desde la propuesta IA original.

## 2. Navegación por etapas
- Cada formulario editable incorpora `Navegación segura`.
- El usuario elige directamente a qué etapa anterior desea volver.
- El botón `Guardar cambios e ir a la etapa seleccionada` envía el formulario y recién después cambia de etapa.
- Se evita el salto superior en pantallas editables porque podía descartar campos que aún no habían sido enviados por Streamlit.

## 3. IA reactiva / análisis vivo
- Un cambio guardado marca automáticamente las etapas dependientes como desactualizadas.
- Al volver a entrar en una etapa dependiente, GearBot ejecuta un refresh inteligente una sola vez.
- Si cambia fenómeno/principio, se actualiza Ishikawa.
- Si cambian causas priorizadas, se reconstruyen 5 Porqués y planes.
- Si el investigador modifica los 5 Porqués, GearBot usa esa edición como fuente de verdad, mejora continuidad pregunta-respuesta y actualiza los planes relacionados.
- Si cambian causas o planes, el informe final se actualiza automáticamente al entrar en Informe.
- No se hacen llamadas IA por cada tecla: la detección ocurre al guardar/avanzar/retroceder.

## 4. Protección de la edición humana
- Los prompts reactivos indican explícitamente que las modificaciones del investigador prevalecen sobre propuestas IA anteriores.
- GearBot puede mejorar coherencia y redacción, pero no debe inventar hechos nuevos.

## Base
- Construida sobre v4.4.2.
- Mantiene Supabase, validaciones, reincidencias, modos de falla e indicadores.
- No requiere cambio de esquema de base de datos.
