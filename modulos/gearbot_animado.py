"""GearBot: animación local con SVG/CSS sobre las ilustraciones originales."""
import base64
from functools import lru_cache
from pathlib import Path
import streamlit as st

@lru_cache(maxsize=2)
def _imagen(nombre):
    return base64.b64encode((Path(__file__).resolve().parents[1]/'assets'/nombre).read_bytes()).decode('ascii')

def html_gearbot(compacto=False):
    nombre='gearbot_small.png' if compacto else 'gearbot_hero.png'
    ancho,alto=(1536,1024) if compacto else (1254,1254)
    # Coordenadas de párpados en el lienzo original; la nariz conserva su ilustración.
    ojos=[(735,375,62,82),(888,378,61,82)] if compacto else [(585,467,74,105),(771,474,73,105)]
    ident='gearbot-small' if compacto else 'gearbot-hero'
    parpados=[]
    textura=[]
    tono='#9e9787' if compacto else '#a09c93'
    for x,y,rx,ry in ojos:
        textura.append(f"<ellipse cx='{x}' cy='{y}' rx='{rx}' ry='{ry}' fill='{tono}'/><path d='M {x-rx*.72} {y} Q {x} {y+ry*.30} {x+rx*.72} {y-3}' fill='none' stroke='#101211' stroke-width='{max(8,rx*.12)}' stroke-linecap='round'/>")
    nariz=("M810 420 Q850 395 872 419 Q884 439 866 455 Q847 472 815 461 L810 452 Q840 462 858 445 Q873 426 852 419 Q834 414 815 426 Z" if compacto else "M675 520 Q715 493 741 513 Q762 535 746 560 Q724 588 682 576 L678 564 Q715 580 734 551 Q747 529 726 520 Q707 514 684 530 Z")
    parpados.append(f"<clipPath id='{ident}-nariz'><path d='{nariz}'/></clipPath>")
    textura.append(f"<use href='#{ident}-original' clip-path='url(#{ident}-nariz)'/>")
    return f"""<style>
.gearbot-motion {{ width:100%; margin:0 auto; padding:8px 4px; box-sizing:border-box; }}
.gearbot-motion svg {{ display:block; width:100%; height:auto; overflow:visible; }}
.gearbot-body {{ transform-box:fill-box; transform-origin:50% 92%; animation:gearbot-sway 4.8s ease-in-out infinite; }}
.gearbot-eyelids {{ opacity:0; animation:gearbot-blink 6.8s linear infinite; }}
@keyframes gearbot-sway {{ 0%,100% {{ transform:translateY(0) rotate(-.6deg); }} 50% {{ transform:translateY(-7px) rotate(.7deg); }} }}
@keyframes gearbot-blink {{ 0%,36%,39%,87%,90%,93%,100% {{ opacity:0; }} 36.7%,38.2%,87.7%,89.2%,91%,92.2% {{ opacity:1; }} }}
@media(prefers-reduced-motion:reduce) {{ .gearbot-body,.gearbot-eyelids {{ animation:none!important; }} }}
</style><div class='gearbot-motion'><svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {ancho} {alto}' role='img' aria-label='GearBot, asistente de NeuralMant, con movimiento suave y parpadeo'><defs><image id='{ident}-original' href='data:image/png;base64,{_imagen(nombre)}' width='{ancho}' height='{alto}'/>{''.join(parpados)}</defs><g class='gearbot-body'><use href='#{ident}-original'/><g class='gearbot-eyelids'>{''.join(textura)}</g></g></svg></div>"""

def mostrar_gearbot(compacto=False):
    st.markdown(html_gearbot(compacto),unsafe_allow_html=True)
