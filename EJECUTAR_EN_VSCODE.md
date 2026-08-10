# Ejecutar RootMine v4.0 en VS Code

## Primera vez

1. Descomprime la carpeta completa.
2. En VS Code: **Archivo > Abrir carpeta** y selecciona `NeuralMant_Suite_RootMine_v4.0`.
3. Abre la terminal integrada.
4. Ejecuta:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Si PowerShell bloquea la activación, ejecuta solo para esa sesión:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

5. Copia `.streamlit/secrets.toml.example` como `.streamlit/secrets.toml` y agrega una sola `GEMINI_API_KEY`.
6. Ejecuta:

```powershell
python -m streamlit run app.py
```

También puedes ejecutar `INSTALAR_ROOTMINE.bat` una vez y luego `INICIAR_ROOTMINE.bat`.

## Maestro v4.0

- Los 104 usuarios de la carga inicial pertenecen internamente al **Centro 1802 - San Vicente**.
- El centro no se selecciona en el login: se obtiene desde el maestro del usuario.
- El flujo de aprobación se resuelve por **Centro + Área + Rol/Responsabilidad**.
- Los centros de futuras plantas se agregan al maestro junto con sus usuarios, sin cambiar el login.
- Correo externo desactivado: se utilizan notificaciones internas.
