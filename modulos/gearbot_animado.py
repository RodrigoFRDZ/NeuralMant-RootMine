"""GearBot con piezas completas y hombros ocultos detrás del cuerpo."""
import base64
from functools import lru_cache
from pathlib import Path
import streamlit as st

@lru_cache(maxsize=4)
def _imagen(nombre):
    archivo=Path(__file__).resolve().parents[1]/'assets/gearbot_rig'/nombre
    return base64.b64encode(archivo.read_bytes()).decode('ascii')

def html_gearbot(compacto=False,modo=None):
    modo=modo or ('bienvenida' if compacto else 'reposo')
    if modo not in ('acceso','bienvenida','reposo'):raise ValueError('Modo de GearBot inválido.')
    ident='gearbot-rig-'+modo+('-small' if compacto else '-hero')
    def imagen(nombre,x,y,w,h,extra=''):
        return f"<image x='{x}' y='{y}' width='{w}' height='{h}' href='data:image/png;base64,{_imagen(nombre)}' {extra}/>"
    saludo=imagen('brazo_saludo.png',-65,140,391,471.5)
    llave=imagen('brazo_llave.png',688,399,425.5,540.5)
    # Alargar solo el tramo recto del pantalón; botas y engranaje conservan su tamaño.
    cuerpo_fuente=imagen('cuerpo.png',0,0,480,650,f"id='{ident}-cuerpo-fuente'")
    cuerpo=f"<g transform='translate(160 50) scale(1.5)'><use href='#{ident}-cuerpo-fuente' clip-path='url(#{ident}-superior)'/><g transform='translate(0 -404) scale(1 1.8)'><use href='#{ident}-cuerpo-fuente' clip-path='url(#{ident}-piernas)'/></g><g transform='translate(0 34.4)'><use href='#{ident}-cuerpo-fuente' clip-path='url(#{ident}-botas)'/></g></g>"
    # Solo la zona de los ojos cambia. Cabeza, casco, boca y cuerpo permanecen fijos.
    cerrados=imagen('cuerpo_cerrado_referencia.png',5,15,500,614,f"clip-path='url(#{ident}-ojos)'")
    return f"""<style>
.gearbot-motion {{ width:100%; margin:0 auto; box-sizing:border-box; }}
.gearbot-motion svg {{ display:block; width:100%; height:auto; }}
.gearbot-saludo {{ transform-origin:245px 520px; }}
.gearbot-llave {{ transform-origin:755px 650px; }}
.gearbot-acceso .gearbot-saludo {{ animation:gearbot-saludo-ciclo-v2 15s ease-in-out infinite; }}
.gearbot-acceso .gearbot-llave {{ animation:gearbot-apuntar-v2 15s ease-in-out infinite; }}
.gearbot-bienvenida .gearbot-saludo {{ animation:gearbot-saludo-inicial-v2 1.8s ease-in-out 1; }}
.gearbot-bienvenida .gearbot-llave {{ transform-origin:1010px 485px; animation:gearbot-ajustar-v2 15s ease-in-out infinite; }}
.gearbot-tuerca {{ opacity:0; }}
.gearbot-bienvenida .gearbot-tuerca {{ animation:gearbot-tuerca-v2 15s linear infinite; }}
.gearbot-eyelids {{ opacity:0; animation:gearbot-blink-v2 6.8s linear infinite; }}
@keyframes gearbot-saludo-inicial-v2 {{ 0%,100% {{ transform:rotate(0deg); }} 23%,63% {{ transform:rotate(5deg); }} 43%,82% {{ transform:rotate(-5deg); }} }}
@keyframes gearbot-saludo-ciclo-v2 {{ 0%,13%,100% {{ transform:rotate(0deg); }} 3%,8% {{ transform:rotate(5deg); }} 5.5%,10.5% {{ transform:rotate(-5deg); }} }}
@keyframes gearbot-apuntar-v2 {{ 0%,17%,39%,100% {{ transform:rotate(0deg); }} 24%,32% {{ transform:rotate(39deg); }} }}
@keyframes gearbot-ajustar-v2 {{ 0%,86%,100% {{ transform:rotate(0deg); }} 89%,95% {{ transform:rotate(4deg); }} 92%,98% {{ transform:rotate(-4deg); }} }}
@keyframes gearbot-tuerca-v2 {{ 0%,84%,100% {{ opacity:0; }} 86%,98% {{ opacity:1; }} }}
@keyframes gearbot-blink-v2 {{ 0%,36%,39%,87%,90%,93%,100% {{ opacity:0; }} 36.7%,38.2%,87.7%,89.2%,91%,92.2% {{ opacity:1; }} }}
@media(max-width:640px) {{ .gearbot-acceso .gearbot-llave {{ animation-name:gearbot-apuntar-abajo-v2; }} }}
@keyframes gearbot-apuntar-abajo-v2 {{ 0%,17%,39%,100% {{ transform:rotate(0deg); }} 24%,32% {{ transform:rotate(95deg); }} }}
@media(prefers-reduced-motion:reduce) {{ .gearbot-saludo,.gearbot-llave,.gearbot-tuerca,.gearbot-eyelids {{ animation:none!important; }} }}
</style><div class='gearbot-motion gearbot-{modo}'><svg xmlns='http://www.w3.org/2000/svg' viewBox='-105 5 1330 1140' role='img' aria-label='GearBot: saludo, gestos con la llave y parpadeo'><defs>{cuerpo_fuente}<clipPath id='{ident}-superior'><rect x='0' y='0' width='480' height='505.1'/></clipPath><clipPath id='{ident}-piernas'><rect x='0' y='504.9' width='480' height='43.2'/></clipPath><clipPath id='{ident}-botas'><rect x='0' y='547.9' width='480' height='102.1'/></clipPath><clipPath id='{ident}-ojos'><ellipse cx='212' cy='285' rx='47' ry='61'/><ellipse cx='327' cy='288' rx='47' ry='60'/></clipPath></defs><g class='gearbot-tuerca'><polygon points='1036,485 1023,508 997,508 984,485 997,462 1023,462' fill='#b9b5aa' stroke='#101211' stroke-width='6'/><circle cx='1010' cy='485' r='8' fill='#575853'/></g><g class='gearbot-saludo'>{saludo}</g><g class='gearbot-llave'>{llave}</g><g class='gearbot-body'>{cuerpo}<g transform='translate(160 50) scale(1.5)'><g class='gearbot-eyelids'>{cerrados}<ellipse cx='286' cy='330' rx='38' ry='29' fill='#aaa79d'/><path d='M267 316 Q287 304 301 317 Q315 332 299 343 Q284 353 268 347' fill='none' stroke='#101211' stroke-width='5' stroke-linecap='round'/></g></g></g></svg></div>"""

def mostrar_gearbot(compacto=False,modo=None):
    st.markdown(html_gearbot(compacto,modo),unsafe_allow_html=True)
