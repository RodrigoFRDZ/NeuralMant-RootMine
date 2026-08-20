# RootMine v4.2.3 — Continuación real de borradores

## Corrección principal
- `Continuar análisis` recupera el mismo ADF y conserva su `adf_id`.
- Restaura `borrador_json`, `borrador_paso` y todo el avance guardado.
- No crea un ADF nuevo al continuar un borrador.

## Corrección de etapa final
- Si un ADF quedó como `Borrador` en el paso 9 (Resumen final), al retomarlo se abre automáticamente en el paso 8 `PDF / envío`.
- Esto evita que el usuario quede atrapado viendo únicamente `Crear otro ADF`.
- Si por cualquier razón un borrador llega al Resumen final, se muestra `← Volver a PDF / envío` en vez de ofrecer crear otro análisis.

## Seguridad visual
- Al retomar un borrador se muestra claramente:
  `Continuando el ADF #X ... no se creará uno nuevo.`

## Compatibilidad
- Mantiene todas las mejoras de v4.2.2.
- No cambia el esquema de Supabase.
- No modifica ni duplica ADF existentes.
