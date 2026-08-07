import streamlit as st


def mostrar_acerca() -> None:
    st.markdown('''<div class="about-hero"><div class="eyebrow">NEURALMANT</div><h1>ROOT<span>MINE</span></h1><p>Suite de inteligencia artificial para mantenimiento industrial. RootMine es el módulo especializado en análisis de causa raíz.</p></div>''',unsafe_allow_html=True)
    c1,c2=st.columns([1,1.15],gap="large")
    with c1:
        st.image("assets/gearbot_hero.png",use_container_width=True)
    with c2:
        st.subheader("GearBot, tu asistente de análisis")
        st.write("GearBot acompaña al usuario durante la identificación del fenómeno, el Ishikawa 6M, los 5 Porqués y la definición del plan de prevención.")
        st.markdown("""
        **Funcionalidades principales**
        - Diagnóstico inicial asistido por IA.
        - Ishikawa ordenado en matriz y vista compacta.
        - Cadenas causales editables de 3 a 5 niveles.
        - Justificación técnica y evidencia requerida.
        - Planes de prevención editables.
        - Informe PDF profesional.
        - Historial e indicadores básicos.
        """)
        st.divider()
        st.markdown("**NeuralMant Suite · RootMine · Versión 3.0**")
        st.markdown("Created by **Rodrigo Fernández**")
        st.caption("La IA entrega recomendaciones preliminares. Toda conclusión debe validarse técnicamente antes de su aprobación.")
