# RootMine v4.1.3 · Borradores persistentes

- Guardado automático al cambiar de etapa.
- Borradores persistidos en Supabase/PostgreSQL cuando `DATABASE_URL` está configurado.
- El ADF conserva el mismo ID desde la primera etapa guardada hasta el informe final.
- Dashboard con sección **ADF en progreso** y botón para continuar.
- Historial con botón **Continuar este borrador**.
- Se guardan respuestas IA, Ishikawa, 5 Porqués, planes e imágenes del borrador.
- El PDF no se duplica dentro del snapshot; se recupera desde `pdf_archivo`.
