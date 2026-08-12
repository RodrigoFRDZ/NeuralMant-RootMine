# Configurar indicadores de cuota de GearBot

RootMine v4.1.6 registra automáticamente cada llamada enviada a Gemini.

Google puede cambiar los límites del Free Tier según el modelo y proyecto.
Consulta los valores vigentes en Google AI Studio > Dashboard > Rate Limit.

Agrega a `.streamlit/secrets.toml` y a Streamlit Community Cloud > Settings > Secrets:

```toml
GEMINI_HOURLY_LIMIT = 0
GEMINI_DAILY_LIMIT = 0
```

Reemplaza `0` por los límites efectivos de tu proyecto.

Ejemplo SOLO ILUSTRATIVO (no copiar sin revisar AI Studio):

```toml
GEMINI_HOURLY_LIMIT = 60
GEMINI_DAILY_LIMIT = 500
```

El administrador verá:
- consultas de los últimos 60 minutos;
- consultas del día;
- intentos rechazados por cuota;
- espacio utilizado y disponible en la base Supabase.

El contador interno de RootMine sirve como control operacional. El dashboard de Google
sigue siendo la fuente oficial de cuota del proyecto.
