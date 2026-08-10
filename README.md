# NeuralMant Suite · RootMine v4.0

RootMine v4.0 es la versión Streamlit preparada para ejecución local en VS Code y para escalar el flujo de ADF por planta, área y rol.

## Cambios de esta compilación

- Login corporativo por correo habilitado en el maestro.
- Diseño de ingreso con GearBot + ROOTMINE y logo NeuralMant nítido.
- Una sola `GEMINI_API_KEY` central para toda la aplicación.
- Los **104 usuarios de la carga inicial** están asociados internamente al **Centro 1802 - San Vicente**.
- El usuario no selecciona centro en el login.
- Al crear un ADF, el centro/planta se completa automáticamente desde el perfil y queda bloqueado para evitar errores de asignación.
- Maestro preparado para otros centros como 1901 Lo Miranda, 1702 Rosario y 7186 La Calera cuando se incorporen sus usuarios.
- Enrutamiento de aprobación por **Centro + Área + Rol/Responsabilidad**, sin una lista fija de `if` por cada jefe.
- Jefaturas con múltiples áreas soportadas mediante `responsable_de`.
- Flujo: `Borrador → Pendiente Supervisor → Pendiente Jefe → Aprobado`.
- Rechazo con comentario obligatorio y trazabilidad.
- Ingeniero con capacidad de reemplazo transversal dentro de su mismo centro.
- Subgerente con vista de pendientes de su centro, sin acciones de aprobación.
- Notificaciones internas; correo externo desactivado durante el piloto.
- Imágenes de falla al inicio y contexto visual de equipo + componente.
- Ishikawa 6M y 5 Porqués editables.
- PDF técnico con evidencia, principio de funcionamiento y plan de prevención.
- Base de conocimiento capaz de recuperar casos de distintos centros.

## Estructura del maestro de usuarios

Cada registro de `data/usuarios_adf.json` puede contener:

- `correo`
- `nombre`
- `centro`
- `planta`
- `area`
- `rol`
- `responsable_de`
- `activo`

Para Supervisor/Jefe, `responsable_de` indica las áreas que puede validar. La búsqueda de responsable se realiza dentro del mismo centro del ADF.

## Configuración IA

Copia `.streamlit/secrets.toml.example` como `.streamlit/secrets.toml`:

```toml
GEMINI_API_KEY = "TU_API_KEY_GEMINI"
GEMINI_MODEL = "gemini-3.1-flash-lite"
EMAIL_NOTIFICATIONS = false
```

No subas `secrets.toml` a GitHub.

## Ejecución rápida en VS Code

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

También puedes usar `INSTALAR_ROOTMINE.bat` y luego `INICIAR_ROOTMINE.bat`.

### Navegación v4.0
En todas las páginas internas aparece **🏠 ROOTMINE · Inicio** en la parte superior. Este botón vuelve directamente al Dashboard principal. El botón ROOTMINE de la barra lateral mantiene la misma función.

## Actualización seguimiento de planes
- Indicadores: tiempo perdido por área/equipo, planes atrasados, por vencer y ejecutados, pendientes de validación.
- Validaciones: descarga de PDF preliminar y visualización de planes antes de aprobar.
- Planes de acción: fecha compromiso, estado, evidencia, NOTI, status SAP, MOV de mercancías, gasto y revisión IA de respaldos.
- Historial: muestra respaldos y última revisión IA de cada acción.
