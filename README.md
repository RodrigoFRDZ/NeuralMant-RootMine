# NeuralMant · RootMine v3.0

Plataforma Streamlit de análisis inteligente de causa raíz, asistida por GearBot.

**Created by Rodrigo Fernández**

# ADF IA v0.9

Versión con flujo de cuatro llamadas controladas:

1. Diagnóstico inicial, fenómeno y principio de funcionamiento.
2. Ishikawa 6M.
3. 5 Porqués y planes preventivos editables.
4. Redacción final del informe.

El PDF se construye localmente con ReportLab e incluye fotografía de la falla o un espacio reservado, principio de funcionamiento, Ishikawa, cadenas causales y plan preventivo.

## Ejecutar

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m streamlit run app.py
```

Configurar `.streamlit/secrets.toml`:

```toml
GEMINI_API_KEY = "TU_CLAVE"
GEMINI_MODEL = "gemini-3.1-flash-lite"
```


## Cambios v1.0
- Ishikawa presentado como matriz 6M uniforme, con espina compacta opcional.
- 5 Porqués con profundidad dinámica entre 3 y 5 niveles.
- Control editable para agregar o quitar niveles causales.
- Validación mínima para evitar análisis superficiales de solo uno o dos niveles.


## Identidad visual
- GearBot oficial con sus zonas blancas opacas y fondo transparente.
- Logo NeuralMant: cerebro/red neuronal integrado con engranaje.
