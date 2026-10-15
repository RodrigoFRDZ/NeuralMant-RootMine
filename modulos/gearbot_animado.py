"""Gestos de GearBot en SVG/CSS: saludo, indicación y ajuste, sin balanceo."""
import base64
from functools import lru_cache
from pathlib import Path
import streamlit as st

@lru_cache(maxsize=1)
def _imagen():
    return base64.b64encode((Path(__file__).resolve().parents[1]/'assets/gearbot_hero.png').read_bytes()).decode('ascii')

def html_gearbot(compacto=False,modo=None):
    modo=modo or ('bienvenida' if compacto else 'reposo')
    if modo not in ('acceso','bienvenida','reposo'):raise ValueError('Modo de GearBot inválido.')
    ident='gearbot-'+modo+('-small' if compacto else '-hero')
    # Cada brazo reutiliza píxeles originales; se separa con máscaras SVG.
    saludo='M0 65 H350 V431 L262 453 L272 480 L263 520 L300 535 L299 607 L220 611 L90 540 L0 405 Z'
    llave='M1030 345 H1254 V1060 H918 V865 L946 819 L917 790 L909 744 L941 689 L965 667 L992 634 L1013 575 Z'
    ojos=[]
    for x,y,rx,ry in [(585,467,74,105),(771,474,73,105)]:
        ojos.append(f"<ellipse cx='{x}' cy='{y}' rx='{rx}' ry='{ry}' fill='#a09c93'/><path d='M {x-rx*.72} {y} Q {x} {y+ry*.30} {x+rx*.72} {y-3}' fill='none' stroke='#101211' stroke-width='9' stroke-linecap='round'/>")
    nariz='M675 520 Q715 493 741 513 Q762 535 746 560 Q724 588 682 576 L678 564 Q715 580 734 551 Q747 529 726 520 Q707 514 684 530 Z'
    # Acceso: saluda, apunta a la derecha y vuelve a reposo cada 15 s.
    # Bienvenida: saludo inicial único; gesto con la llave al final de cada ciclo de 15 s.
    return f"""<style>
.gearbot-motion {{ width:100%; margin:0 auto; padding:5px 0; box-sizing:border-box; }}
.gearbot-motion svg {{ display:block; width:100%; height:auto; overflow:visible; }}
.gearbot-saludo {{ transform-origin:299px 565px; }}
.gearbot-llave {{ transform-origin:949px 731px; }}
.gearbot-acceso .gearbot-saludo {{ animation:gearbot-saludo-ciclo 15s ease-in-out infinite; }}
.gearbot-acceso .gearbot-llave {{ animation:gearbot-apuntar 15s ease-in-out infinite; }}
.gearbot-bienvenida .gearbot-saludo {{ animation:gearbot-saludo-inicial 2.1s ease-in-out 1; }}
.gearbot-bienvenida .gearbot-llave {{ transform-origin:1155px 420px; animation:gearbot-ajustar 15s ease-in-out infinite; }}
.gearbot-tuerca {{ opacity:0; }}
.gearbot-bienvenida .gearbot-tuerca {{ animation:gearbot-tuerca 15s linear infinite; }}
.gearbot-eyelids {{ opacity:0; animation:gearbot-blink 6.8s linear infinite; }}
@keyframes gearbot-saludo-inicial {{ 0%,100% {{ transform:rotate(0deg); }} 20%,60% {{ transform:rotate(10deg); }} 40%,80% {{ transform:rotate(-8deg); }} }}
@keyframes gearbot-saludo-ciclo {{ 0%,14%,100% {{ transform:rotate(0deg); }} 3%,9% {{ transform:rotate(10deg); }} 6%,12% {{ transform:rotate(-8deg); }} }}
@keyframes gearbot-apuntar {{ 0%,17%,40%,100% {{ transform:rotate(0deg); }} 23%,33% {{ transform:rotate(54deg); }} }}
@keyframes gearbot-ajustar {{ 0%,86%,100% {{ transform:rotate(0deg); }} 89%,95% {{ transform:rotate(8deg); }} 92%,98% {{ transform:rotate(-7deg); }} }}
@keyframes gearbot-tuerca {{ 0%,84%,100% {{ opacity:0; }} 86%,98% {{ opacity:1; }} }}
@keyframes gearbot-blink {{ 0%,36%,39%,87%,90%,93%,100% {{ opacity:0; }} 36.7%,38.2%,87.7%,89.2%,91%,92.2% {{ opacity:1; }} }}
@media(max-width:640px) {{ .gearbot-acceso .gearbot-llave {{ animation-name:gearbot-apuntar-abajo; }} }}
@keyframes gearbot-apuntar-abajo {{ 0%,17%,40%,100% {{ transform:rotate(0deg); }} 23%,33% {{ transform:rotate(118deg); }} }}
@media(prefers-reduced-motion:reduce) {{ .gearbot-saludo,.gearbot-llave,.gearbot-tuerca,.gearbot-eyelids {{ animation:none!important; }} }}
</style><div class='gearbot-motion gearbot-{modo}'><svg xmlns='http://www.w3.org/2000/svg' viewBox='-85 -55 1520 1370' role='img' aria-label='GearBot, asistente de NeuralMant: saludo, gestos con la llave y parpadeo'><defs><image id='{ident}-original' href='data:image/png;base64,{_imagen()}' width='1254' height='1254'/><clipPath id='{ident}-saludo'><path d='{saludo}'/></clipPath><clipPath id='{ident}-llave'><path d='{llave}'/></clipPath><clipPath id='{ident}-nariz'><path d='{nariz}'/></clipPath><mask id='{ident}-cuerpo' maskUnits='userSpaceOnUse' x='0' y='0' width='1254' height='1254'><rect width='1254' height='1254' fill='white'/><path d='{saludo}' fill='black'/><path d='{llave}' fill='black'/></mask></defs><g class='gearbot-body'><use href='#{ident}-original' mask='url(#{ident}-cuerpo)'/><g class='gearbot-saludo'><use href='#{ident}-original' clip-path='url(#{ident}-saludo)'/></g><g class='gearbot-tuerca'><polygon points='1191,420 1173,451 1137,451 1119,420 1137,389 1173,389' fill='#b9b5aa' stroke='#101211' stroke-width='8'/><circle cx='1155' cy='420' r='12' fill='#575853' stroke='#101211' stroke-width='5'/></g><g class='gearbot-llave'><use href='#{ident}-original' clip-path='url(#{ident}-llave)'/></g><g class='gearbot-eyelids'>{''.join(ojos)}<use href='#{ident}-original' clip-path='url(#{ident}-nariz)'/></g></g></svg></div>"""

def mostrar_gearbot(compacto=False,modo=None):
    st.markdown(html_gearbot(compacto,modo),unsafe_allow_html=True)
