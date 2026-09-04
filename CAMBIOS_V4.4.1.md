# RootMine v4.4.1 — FIX ADF similares por equipo

- La búsqueda de antecedentes similares se limita al mismo activo.
- Si existe N° de equipo, la coincidencia se hace por ese identificador.
- Si no existe N° de equipo, se exige coincidencia exacta de la descripción normalizada.
- Palabras genéricas como motor, falla, rodamiento, alarma, etc. ya no relacionan equipos distintos.
- Los ADF anteriores del mismo equipo se muestran solo como referencia.
- La existencia de antecedentes nunca bloquea la creación de un nuevo ADF.
- GearBot solo recibe como contexto histórico los ADF del mismo activo.
- Mantiene análisis vivo, navegación dinámica y todas las mejoras de v4.4.0.
