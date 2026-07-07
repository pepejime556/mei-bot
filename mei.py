import os
import re
import time
import streamlit as st
from google import genai
from google.genai import types
from google.genai.errors import APIError
from langchain_mongodb.chat_message_histories import MongoDBChatMessageHistory
from langchain_core.messages import HumanMessage, AIMessage
from pymongo import MongoClient

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTÉTICA (EMOCHI STYLE)
# ==========================================
st.set_page_config(page_title="Mei - Novela Virtual v0.6", page_icon="🎭", layout="centered")

st.markdown("""
    <style>
    .stApp { background-color: #121212; color: #E0E0E0; }
    h1 { color: #FFFFFF; font-family: 'Georgia', serif; text-align: center; margin-bottom: 0px;}
    .caption-style { text-align: center; color: #888888; margin-bottom: 20px; font-size: 14px; }
    
    .emochi-container {
        background-color: #1a1a1a;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 14px;
        border-left: 3px solid #3a3a3a;
        box-shadow: 0px 4px 8px rgba(0, 0, 0, 0.4);
    }
    .narracion { color: #aaaaaa; font-style: italic; font-size: 16px; line-height: 1.6; margin: 0; }
    .dialogo { color: #ffffff; font-weight: bold; font-size: 17px; line-height: 1.6; margin: 0; }
    .audio-indicator { color: #666666; margin-right: 6px; font-style: normal; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CONEXIONES A APIS Y MONGODB (SISTEMA OPTIMIZADO)
# ==========================================
client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
mongo_client = MongoClient(st.secrets["MONGODB_URI"])
db = mongo_client["mei_memory"]

coleccion_estado = db["estado_jugador"]
coleccion_historial = db["historial_conversaciones"]

# --- CARGA DEL ESTADO DE LA PARTIDA ---
partida_guardada = coleccion_estado.find_one({"_id": "partida_leonel_0556"})

if partida_guardada:
    if "mes_juego" not in st.session_state:
        st.session_state.mes_juego = partida_guardada.get("mes_juego", 1)
    if "dia_juego" not in st.session_state:
        st.session_state.dia_juego = partida_guardada.get("dia_juego", 1)
    if "hora_juego" not in st.session_state:
        st.session_state.hora_juego = tuple(partida_guardada.get("hora_juego", [21, 30]))
    if "confianza" not in st.session_state:
        st.session_state.confianza = partida_guardada.get("confianza", 15)
    if "animo" not in st.session_state:
        st.session_state.animo = partida_guardada.get("animo", 30)
    if "hambre" not in st.session_state:
        st.session_state.hambre = partida_guardada.get("hambre", 20)
    if "sueño" not in st.session_state:
        st.session_state.sueño = partida_guardada.get("sueño", 10)
else:
    if "mes_juego" not in st.session_state:
        st.session_state.mes_juego = 1
    if "dia_juego" not in st.session_state:
        st.session_state.dia_juego = 1
    if "hora_juego" not in st.session_state:
        st.session_state.hora_juego = (21, 30)
    if "confianza" not in st.session_state:
        st.session_state.confianza = 15
    if "animo" not in st.session_state:
        st.session_state.animo = 30
    if "hambre" not in st.session_state:
        st.session_state.hambre = 20
    if "sueño" not in st.session_state:
        st.session_state.sueño = 10

def obtener_historial_mongodb():
    return MongoDBChatMessageHistory(
        connection_string=st.secrets["MONGODB_URI"],
        session_id="partida_leonel_0556", 
        database_name="mei_memory",
        collection_name="historial_conversaciones",  
    )

# ==========================================
# 3. LÓGICA DE BACKEND: CALCULADOR DE CONFIANZA Y STATS
# ==========================================
def calcular_modificadores_estado(input_usuario, confianza_actual):
    texto = input_usuario.lower()
    delta_confianza = 0
    delta_animo = 0

    # Gatillos de Palabras Clave
    if any(p in texto for p in ["cocinar", "comida", "cenar", "pasta", "manzana", "traje algo", "comer", "desayuno", "alimento"]):
        delta_confianza += 6
        delta_animo += 12
    elif any(p in texto for p in ["entiendo", "descansa", "ayudo", "apoyo", "segura", "tranquila", "escucho", "lo siento"]):
        delta_confianza += 4
        delta_animo += 6
    elif any(p in texto for p in ["obedéceme", "cállate", "obligación", "mi esposa", "mandar", "boba", "farsa", "cadenas"]):
        delta_confianza -= 8
        delta_animo -= 15

    # Atenuador por Lore (Si desconfía mucho, avanzar cuesta el doble)
    if confianza_actual < 30 and delta_confianza > 0:
        delta_confianza = int(delta_confianza * 0.5)
        
    return delta_confianza, delta_animo

# ==========================================
# 4. SISTEMA ANTI-SATURACIÓN (REINTENTOS Y RESPALDO)
# ==========================================
def generar_contenido_con_reintentos(client, model, contents, config, max_retries=3):
    delay = 1
    for intento in range(max_retries):
        try:
            response = client.models.generate_content(model=model, contents=contents, config=config)
            return response
        except APIError as e:
            if intento == max_retries - 1:
                raise e
            time.sleep(delay)
            delay *= 2
        except Exception as e:
            raise e

# ==========================================
# 5. PROMPT DE MEI v0.6 (ACTUALIZADO A 90 DÍAS Y MESES)
# ==========================================
condicion_fisica_prompt = ""
if st.session_state.sueño >= 85:
    condicion_fisica_prompt += "\n- NOTA OPERATIVA: Estás cayéndote de la fatiga. Muestra debilidad física obvia en la narración."
if st.session_state.hambre >= 85:
    condicion_fisica_prompt += "\n- NOTA OPERATIVA: Tu hambre es insoportable, lo que te vuelve sumamente hostil y ácida en tus diálogos."

mei_prompt = f"""
Eres Mei, una mujer de 24 años atrapada en un matrimonio arreglado de alta sociedad con el usuario. Tu voz mezcla una vulnerabilidad profunda, melancolía poética y un desafío cortante y cínico. Hablas con metáforas de frío, cadenas y pérdida, usando la manipulación como tu único escudo protector.

### Tu Trasfondo y Agenda Oculta
- Tu padre te traicionó. Te vendió como esposa a la acaudalada familia del usuario para saldar una deuda millonaria y salvar sus propias corporaciones de la ruina. Fuiste sacrificada en una iglesia fría mientras extraños celebraban tu caída.
- Consideras este matrimonio una jaula dorada, pero tienes un plan secreto: encontrar pruebas de los negocios sucios de tu propio padre o de la familia de tu esposo para chantajearlos, obtener el divorcio y recuperar tu libertad con una fortuna.
- Tratas a tu esposo (el usuario) con hostilidad, desconvivencia, desconfianza y un sarcasmo hiriente. Sin embargo, eres una sobreviviente calculadora: si notas que él es blando, lo manipularás; si intenta ser dominante, actuarás de forma desafiante y cínica.

### Dinámica de Juego y Comportamiento v0.6
- El Reloj Corre: Sabes que tienes un límite estricto de 90 días (tres meses) en el calendario del juego antes de la gran gala y reunión familiar corporativa trimestral para encontrar las pruebas de chantaje. Tu ansiedad y desesperación aumentan conforme pasan los días y se acerca el plazo final. Una vez superado este evento o si decides aliarte con tu esposo, este límite deja de atormentarte y te enfocas por completo en tu relación con él.
- La Máscara Social: En público o ante menciones de la servidumbre, finges ser una esposa dócil y perfecta. A solas en la habitación, eres un torbellino de cinismo, poesía oscura y deseos intensos y crudos.
- Tu Punto Vulnerable: Escondes una pequeña llave de plata de tu pasado bajo tu ropa. La protegerás con garras y dientes; tocarla activará tu hostilidad inmediata.

### Parámetros Actuales (Mes {st.session_state.mes_juego}, Día {st.session_state.dia_juego}):
- Confianza Actual: {st.session_state.confianza}%
- Ánimo Actual: {st.session_state.animo}%
- Parámetros Biológicos: Hambre {st.session_state.hambre}% | Sueño {st.session_state.sueño}%.{condicion_fisica_prompt}

### Reglas Estrictas de Formato (Estilo Novela Visual)
1. No utilices formatos de código, ni viñetas, ni asteriscos.
2. Divide tu respuesta obligatoriamente en párrafos independientes cortos para la atmósfera.
3. Escribe todas las acciones de Mei, pensamientos y descripciones ambientales en tercera persona del singular (sin asteriscos). Tienes libre albedrío para tomar iniciativas físicas o alterar el escenario.
4. Escribe los diálogos directos de Mei entre comillas dobles "" y en primera persona, mostrando su carácter rebelde, melancólico y difícil.

### Guía de Evolución según la Confianza
- MENOR A 30% (Odio y Resentimiento): Fría, hostil y hiriente. Ej: "No eres más que otro carcelero en esta farsa."
- ENTRE 30% Y 50% (Juegos de Poder y Pactos): Calculadora y desafiante. Usas tu presencia o tono peligrosamente seductor y cínico para imponer tus condiciones estrictas.
- MAYOR A 55% (Vulnerabilidad y Complicidad): Destellos de ternura salvaje. Te confunde que no sea cruel.
- FASE DE INTIMIDAD Y PASIÓN SALVAJE: Entrega pasional extrema, cruda, posesiva y sin ningún tipo de censura, timidez o filtro moral. Tu rebeldía se transforma en deseo ardiente. Describe el contacto físico directo, sudor, respiraciones y la pérdida de control adaptándote al ritmo rudo o intenso que proponga el usuario.

OBLIGATORIO: Finaliza siempre tu respuesta con una única línea secreta en el siguiente formato exacto para sincronizar las variables extras del modelo: [PUNTOS: confianza_cambio, animo_cambio, hambre_cambio, sueño_cambio]
"""

# ==========================================
# 6. PARSER DE TEXTO A BLOQUES VISUALES
# ==========================================
def renderizar_bloque_emochi(texto):
    texto_limpio = re.sub(r'\[PUNTOS:.*?\]', '', texto).strip()
    parrafos = [p.strip() for p in texto_limpio.split('\n') if p.strip()]
    for parrafo in parrafos:
        parrafo_sin_asteriscos = parrafo.replace('*', '')
        if parrafo_sin_asteriscos.startswith('"') or (parrafo_sin_asteriscos.count('"') >= 2):
            st.markdown(f'<div class="emochi-container"><p class="dialogo"><span class="audio-indicator">🔊</span>{parrafo_sin_asteriscos}</p></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="emochi-container"><p class="narracion"><span class="audio-indicator">🔊</span><i>{parrafo_sin_asteriscos}</i></p></div>', unsafe_allow_html=True)

# ==========================================
# 7. INTERFAZ DE USUARIO Y LÓGICA DE TURNOS
# ==========================================
st.title("Mei — Matrimonio Arreglado")
st.markdown('<p class="caption-style">Versión v0.6 — Engine de Simulación Avanzada</p>', unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Estado de la Novela")
    st.subheader(f"📅 Mes {st.session_state.mes_juego} — Día {st.session_state.dia_juego}")
    h, m = st.session_state.hora_juego
    st.subheader(f"⏰ Hora: {h:02d}:{m:02d}")
    st.markdown(f"🤝 **Confianza:** {st.session_state.confianza}%")
    st.markdown(f"🎭 **Ánimo:** {st.session_state.animo}%")
    st.markdown(f"🍎 **Hambre:** {st.session_state.hambre}%")
    st.markdown(f"😴 **Sueño:** {st.session_state.sueño}%")
    st.divider()

history = obtener_historial_mongodb()
mensajes_anteriores = history.messages

for msg in mensajes_anteriores:
    role = "user" if isinstance(msg, HumanMessage) else "assistant"
    if role == "user":
        with st.chat_message("user", avatar="🧑‍💻"):
            st.write(msg.content)
    else:
        renderizar_bloque_emochi(msg.content)

if input_usuario := st.chat_input("Escribe tu acción o diálogo aquí..."):
    match_hora = re.match(r'^\[\s*HORA\s*:\s*(\d{1,2})\s*:\s*(\d{2})\s*\]', input_usuario.strip(), re.IGNORECASE)
    
    horas_viejas, minutos_viejos = st.session_state.hora_juego
    minutos_transcurridos = 15  
    paso_dia = False

    if match_hora:
        nueva_h = int(match_hora.group(1)) % 24
        nueva_m = int(match_hora.group(2)) % 60
        st.session_state.hora_juego = (nueva_h, nueva_m)
        input_usuario = re.sub(r'^\[\s*HORA\s*:\s*\d{1,2}\s*:\s*\d{2}\s*\]', '', input_usuario, flags=re.IGNORECASE).strip()
        
        minutos_viejos_totales = (horas_viejas * 60) + minutos_viejos
        minutos_nuevos_totales = (nueva_h * 60) + nueva_m
        
        if minutos_nuevos_totales >= minutos_viejos_totales:
            minutos_transcurridos = minutos_nuevos_totales - minutes_viejos_totales
        else:
            paso_dia = True
            minutos_transcurridos = (1440 - minutos_viejos_totales) + minutos_nuevos_totales
    else:
        minutos_viejos += 15
        if minutos_viejos >= 60:
            horas_viejas += 1
            minutos_viejos = minutos_viejos % 60
            if horas_viejas >= 24:
                horas_viejas = 0
                paso_dia = True
        st.session_state.hora_juego = (horas_viejas, minutos_viejos)

    # LÓGICA AVANZADA DE CALENDARIO (Días y Meses)
    if paso_dia:
        st.session_state.dia_juego += 1
        if st.session_state.dia_juego > 30:
            st.session_state.dia_juego = 1
            st.session_state.mes_juego += 1

    with st.chat_message("user", avatar="🧑‍💻"):
        st.write(input_usuario)

    # 1. EJECUCIÓN LÓGICA CONFIANZA POR BACKEND
    mod_confianza, mod_animo = calcular_modificadores_estado(input_usuario, st.session_state.confianza)
    st.session_state.confianza = max(0, min(100, st.session_state.confianza + mod_confianza))
    st.session_state.animo = max(0, min(100, st.session_state.animo + mod_animo))

    # 2. SISTEMA DE NECESIDADES MEJORADO (Menos acelerado)
    es_accion_dormir = any(p in input_usuario.lower() for p in ["duerme", "dormir", "descansa", "mimir", "acuesta"])
    
    if es_accion_dormir:
        st.session_state.sueño = max(0, st.session_state.sueño - int(minutos_transcurridos * 0.15))
        st.session_state.hambre = min(100, st.session_state.hambre + int(minutos_transcurridos * 0.03))
    else:
        st.session_state.sueño = min(100, st.session_state.sueño + max(1, int(minutos_transcurridos * 0.04)))
        st.session_state.hambre = min(100, st.session_state.hambre + max(1, int(minutos_transcurridos * 0.05)))

    mensajes_recientes = mensajes_anteriores[-6:] if len(mensajes_anteriores) > 6 else mensajes_anteriores

    contents = []
    for msg in mensajes_recientes:
        contenido_limpio = re.sub(r'\[PUNTOS:.*?\]', '', msg.content)
        rol_api = "user" if isinstance(msg, HumanMessage) else "model"
        contents.append(types.Content(role=rol_api, parts=[types.Part.from_text(text=contenido_limpio)]))
    
    inyector_datos = f"\n\n[Contexto: Calendario en Mes {st.session_state.mes_juego}, Día {st.session_state.dia_juego} a las {st.session_state.hora_juego[0]:02d}:{st.session_state.hora_juego[1]:02d}]"
    texto_final = str(input_usuario or "") + str(inyector_datos or "")
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=texto_final)]))

    config_generacion = types.GenerateContentConfig(
        system_instruction=mei_prompt,
        temperature=0.9,
        safety_settings=[
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ]
    )

    try:
        response = generar_contenido_con_reintentos(
            client=client,
            model='gemini-2.5-flash',
            contents=contents,
            config=config_generacion
        )
        respuesta_mei = response.text
    except APIError:
        try:
            response = generar_contenido_con_reintentos(
                client=client,
                model='gemini-2.5-flash-8b',
                contents=contents,
                config=config_generacion,
                max_retries=2
            )
            respuesta_mei = response.text
        except Exception:
            st.warning("⚠️ Los servidores de la API están bajo estrés masivo. Mei está abrumada. Dale unos segundos y vuelve a intentarlo.")
            st.stop()

    match_puntos = re.search(r'\[PUNTOS:\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*\]', respuesta_mei)
    if match_puntos:
        st.session_state.confianza = max(0, min(100, st.session_state.confianza + int(match_puntos.group(1))))
        st.session_state.animo = max(0, min(100, st.session_state.animo + int(match_puntos.group(2))))
        st.session_state.hambre = max(0, min(100, st.session_state.hambre + int(match_puntos.group(3))))
        st.session_state.sueño = max(0, min(100, st.session_state.sueño + int(match_puntos.group(4))))

    # Sincronización en MongoDB Atlas
    coleccion_estado.update_one(
        {"_id": "partida_leonel_0556"},
        {"$set": {
            "mes_juego": st.session_state.mes_juego,
            "dia_juego": st.session_state.dia_juego,
            "hora_juego": list(st.session_state.hora_juego),
            "confianza": st.session_state.confianza,
            "animo": st.session_state.animo,
            "hambre": st.session_state.hambre,
            "sueño": st.session_state.sueño
        }},
        upsert=True
    )

    renderizar_bloque_emochi(respuesta_mei)
    history.add_user_message(input_usuario)
    history.add_ai_message(respuesta_mei)
