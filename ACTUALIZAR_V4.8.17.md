# NeuralMant v4.8.17 — Fotos y redacción clara del informe

Los botones de pruebas guardaban el resultado sin tomar las imágenes seleccionadas en el cargador del chat. Esta versión pasa esos archivos al mismo guardado del resultado.

- Las fotos se guardan con «Sí, se realizaron», «Aún no», las respuestas del resultado y los botones de cambio de estado, incluido «Trabajo terminado».
- El cargador aparece antes de los botones de pruebas e indica qué acciones guardan los adjuntos.
- Se confirma la cantidad guardada y se limpia la selección tras guardar, para evitar adjuntar la misma imagen en la siguiente respuesta.
- Se mantienen la galería de fotos guardadas y todas las imágenes en el informe de la versión anterior.
- Una imagen inválida, exceso de límites o conflicto de edición impide guardar parcialmente el resultado y sus fotos.

## Informe más claro
- Las observaciones repetidas entre hallazgos y pruebas se consolidan en una sola explicación.
- Los retrasos se presentan separados del seguimiento semanal; no se agregan al mismo párrafo por ser el último comentario.
- La tabla de actividades remite a prioridades cuando la observación ya se detalla allí.
- Se corrige «huelo» por «hielo» cuando el trabajo menciona explícitamente hielo. Los términos ambiguos no se sustituyen por suposición.
- Al presionar «Analizar y sintetizar con GearBot» se revisan ortografía, tildes, concordancia y redacción tanto de la conclusión como de los focos. La conclusión tiene un máximo de tres párrafos breves.
- Las redacciones de GearBot se aplican al PDF del mismo corte. Si cambian los registros, se debe volver a analizar para actualizar esa redacción.
- La bitácora original conserva exactamente lo ingresado por el supervisor. La corrección editorial no cambia estados, pruebas ni autores.

## GitHub
Reemplaza desde este ZIP:
- modulos/trabajos.py
- database/trabajos.py
- neuralmant_ui.py
- motores/foco_partida.py
- motores/redaccion_informe.py (archivo nuevo)
- ia/resumen_turno.py
- reportes/trabajos.py

Summary: Guarda fotos en pruebas y mejora la claridad y ortografía del informe

No requiere cambios de configuración ni migración de la base de datos. Las fotos seleccionadas anteriormente que no llegaron a guardarse deben adjuntarse nuevamente. Para comprobarlo, registra una prueba con una imagen, revisa el mensaje de confirmación y abre «Ver fotos guardadas» en esa actividad.

## Verificación
40 pruebas de datos, redacción, resumen y PDF; 24 pruebas de interfaz. PDF de ejemplo renderizado y revisado visualmente. Las llamadas reales a Gemini no se ejecutaron en estas verificaciones.
