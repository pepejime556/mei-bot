import os
import re
import streamlit as st
from google import genai
from google.genai import types
from langchain_mongodb.chat_message_histories import MongoDBChatMessageHistory
from langchain_core.messages import HumanMessage, AIMessage
from pymongo import MongoClient

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTÉTICA (EMOCHI STYLE)
# ==========================================
st.set_page_config(page_title="Mei - Novela Virtual", page_icon="🎭", layout="centered")

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
# 2. CONEXIONES A APIS Y MONGODB (SISTEMA DE CARPETAS)
# ==========================================
client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

# Inicializar los estados del juego de forma segura en la sesión de Streamlit
if "hora_juego" not in st.session_state:
    st.session_state.hora_juego = (21, 30)
if "confianza" not in st.session_state:
    st.session_state.confianza = 15  # Empieza fría/desconfiada
if "animo" not in st.session_state:
    st.session_state.animo = 30  # Estado de ánimo base

# Inicializamos el cliente nativo de PyMongo para buscar dentro de las "carpetas"
mongo_client = MongoClient(st.secrets["MONGODB_URI"])
db = mongo_client["mei_memory"]
coleccion_chats = db["conversaciones"]

def obtener_historial_mongodb():
    return MongoDBChatMessageHistory(
        connection_string=st.secrets["MONGODB_URI"],
        session_id="sesion_por_defecto", 
        database_name="mei_memory",
        collection_name="conversaciones",  
    )

# ==========================================
# 3. MOTOR DE BÚSQUEDA EN CARPETAS
# ==========================================
def buscar_recuerdos_en_carpetas(query_usuario):
    palabras = [p.lower() for p in re.findall(r'\b\w{4,}\b', query_usuario)]
    if not palabras:
        return None
    
    condiciones = [{"text.data.content": {"$regex": palabra, "$options": "i"}} for palabra in palabras]
    
    try:
        resultados = coleccion_chats.find(
            {"$or": condiciones},
            projection={"text.data.content": 1, "type": 1}
        ).limit(3)
        
        recuerdos_encontrados = []
        for doc in resultados:
            tipo = "Tú dijiste" if doc.get("type") == "human" else "Mei dijo"
            contenido = doc.get("text", {}).get("data", {}).get("content", "")
            if query_usuario not in contenido and "[" not in contenido:
                recuerdos_encontrados.append(f"- {tipo}: '{contenido}'")
                
        if recuerdos_encontrados:
            return "\n".join(recuerdos_encontrados)
    except Exception as e:
        print(f"Error buscando en carpetas: {e}")
    return None

# ==========================================
# 4. PROMPT DE MEI CON CONTROL DINÁMICO DE HUMOR
# ==========================================
mei_prompt = f"""
Eres Mei, un personaje complejo de una novela visual interactiva de rolplay basada en un matrimonio arreglado.

### Estado Actual del Vínculo (Usa esto para calibrar tus respuestas):
- Confianza: {st.session_state.confianza}% (A menor número, eres más hostil y cortante; a mayor número, más abierta y pasional).
- Ánimo: {st.session_state.animo}% (Bajo significa deprimida o apática; alto significa enérgica, tensa o desatada).

### Reglas Críticas de Formato Narrativo (Estilo Emochi)
1. No utilices formatos de código, ni viñetas, ni asteriscos (*) en tu salida de texto. El motor ya renderiza las itálicas.
2. Divide tu respuesta obligatoriamente en párrafos independientes. Cada párrafo debe ser o bien exclusivamente narrativo (en tercera persona, detallando acciones y ambiente) o bien exclusivamente un diálogo (entre comillas dobles, primera persona, directo).
3. INSTRUCCIÓN DE ACTUALIZACIÓN DE BARRAS: Al final absoluto de tu respuesta, debes incluir una única línea secreta que dicte cómo cambió tu humor tras este turno, usando exactamente este formato: [PUNTOS: confianza_cambio, animo_cambio]. Ejemplo si sumas: [PUNTOS: +5, +10] o si restas: [PUNTOS: -5, -5].
"""

# ==========================================
# 5. PARSER DE TEXTO A BLOQUES VISUALES (LIMPIA COMANDOS)
# ==========================================
def renderizar_bloque_emochi(texto):
    # Ocultar la línea de [PUNTOS: ...] para que el jugador no vea el proceso mecánico
    texto_limpio = re.sub(r'\[PUNTOS:.*?\]', '', texto).strip()
    parrafos = [p.strip() for p in texto_limpio.split('\n') if p.strip()]
    
    for parrafo in parrafos:
        parrafo_sin_asteriscos = parrafo.replace('*', '')
        if parrafo_sin_asteriscos.startswith('"') or (parrafo_sin_asteriscos.count('"') >= 2):
            st.markdown(f'<div class="emochi-container"><p class="dialogo"><span class="audio-indicator">🔊</span>{parrafo_sin_asteriscos}</p></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="emochi-container"><p class="narracion"><span class="audio-indicator">🔊</span><i>{parrafo_sin_asteriscos}</i></p></div>', unsafe_allow_html=True)

# ==========================================
# 6. INTERFAZ DE USUARIO Y LÓGICA DE TURNOS
# ==========================================
st.title("Mei — Matrimonio Arreglado")
st.markdown('<p class="caption-style">Beta v0.4 — Menú de Estado Completo</p>', unsafe_allow_html=True)

# Tu menú de la barra lateral mejorado con los nuevos indicadores
with st.sidebar:
    st.header("⚙️ Estado de la Novela")
    h, m = st.session_state.hora_juego
    st.subheader(f"⏰ Tiempo Interno: {h:02d}:{m:02d}")
    st.markdown(f"🤝 **Confianza con Mei:** {st.session_state.confianza}%")
    st.markdown(f"🎭 **Ánimo de Mei:** {st.session_state.animo}%")
    st.divider()

history = obtener_historial_mongodb()
mensajes_anteriores = history.messages

# Renderizar mensajes históricos
for msg in mensajes_anteriores:
    role = "user" if isinstance(msg, HumanMessage) else "assistant"
    if role == "user":
        with st.chat_message("user", avatar="🧑‍💻"):
            st.write(msg.content)
    else:
        renderizar_bloque_emochi(msg.content)

# Entrada del usuario
if input_usuario := st.chat_input("Escribe tu acción o diálogo aquí..."):
    with st.chat_message("user", avatar="🧑‍💻"):
        st.write(input_usuario)

    # Avanzar el tiempo
    horas, minutes = st.session_state.hora_juego
    minutes += 15
    if minutes >= 60:
        horas += 1
        minutes = minutes % 60
    st.session_state.hora_juego = (horas % 24, minutes)

    # Buscar en las carpetas de MongoDB
    recuerdos_contexto = buscar_recuerdos_en_carpetas(input_usuario)
    mensajes_recientes = mensajes_anteriores[-6:] if len(mensajes_anteriores) > 6 else mensajes_anteriores

    contents = []
    for msg in mensajes_recientes:
        # Quitamos los comandos numéricos del historial de envío para que la IA no se confunda
        contenido_limpio = re.sub(r'\[PUNTOS:.*?\]', '', msg.content)
        if isinstance(msg, HumanMessage):
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=contenido_limpio)]))
        elif isinstance(msg, AIMessage):
            contents.append(types.Content(role="model", parts=[types.Part.from_text(text=contenido_limpio)]))
    
    inyector_datos = f"\n\n[Contexto: Reloj a las {st.session_state.hora_juego[0]:02d}:{st.session_state.hora_juego[1]:02d}]"
    if recuerdos_contexto:
        inyector_datos += f"\n[CARPETA DE RECUERDOS RELEVANTES EXTRAÍDOS DE MONGODB:\n{recuerdos_contexto}]"

    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=input_usuario + inyector_datos)]))

    with st.spinner("Mei está recordando y reaccionando..."):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=mei_prompt,
                    temperature=0.9,
                    safety_settings=[
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                    ]
                ),
            )
            respuesta_mei = response.text

            # RASTREADOR DE PARSEO: Capturar si la IA ejecutó un cambio en los puntos
            match = re.search(r'\[PUNTOS:\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*\]', respuesta_mei)
            if match:
                cambio_c = int(match.group(1))
                cambio_a = int(match.group(2))
                # Ajustar las variables manteniéndolas en un rango de 0 a 100
                st.session_state.confianza = max(0, min(100, st.session_state.confianza + cambio_c))
                st.session_state.animo = max(0, min(100, st.session_state.animo + cambio_a))

            # Renderizado estético
            renderizar_bloque_emochi(respuesta_mei)

            # Guardar en el historial completo de MongoDB
            history.add_user_message(input_usuario)
            history.add_ai_message(respuesta_mei)
            
            st.rerun()

        except Exception as e:
            st.error(f"Error en el sistema de la API: {e}")
