import os
import re
import streamlit as st
from google import genai
from google.genai import types
from langchain_mongodb.chat_message_histories import MongoDBChatMessageHistory
from langchain_core.messages import HumanMessage, AIMessage
from pymongo import MongoClient

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTÉTIICA (EMOCHI STYLE)
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

if "hora_juego" not in st.session_state:
    st.session_state.hora_juego = (21, 30)

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
# 3. MOTOR DE BÚSQUEDA EN CARPETAS (LA MAGIA)
# ==========================================
def buscar_recuerdos_en_carpetas(query_usuario):
    """
    Simula la apertura de 'carpetas' en la base de datos.
    Busca palabras clave importantes en los mensajes viejos guardados en MongoDB
    para extraer recuerdos relevantes sin saturar al modelo.
    """
    # Extraemos palabras clave del mensaje del usuario (quitando conectores cortos)
    palabras = [p.lower() for p in re.findall(r'\b\w{4,}\b', query_usuario)]
    if not palabras:
        return None
    
    # Creamos un filtro de búsqueda en MongoDB: que el historial contenga alguna de estas palabras
    condiciones = [{"text.data.content": {"$regex": palabra, "$options": "i"}} for palabra in palabras]
    
    try:
        # Buscamos mensajes antiguos del asistente (Mei) o Usuario que coincidan
        resultados = coleccion_chats.find(
            {"$or": condiciones},
            projection={"text.data.content": 1, "type": 1}
        ).limit(3) # Extraemos máximo 3 recuerdos clave para no gastar tokens
        
        recuerdos_encontrados = []
        for doc in resultados:
            tipo = "Tú dijiste" if doc.get("type") == "human" else "Mei dijo"
            contenido = doc.get("text", {}).get("data", {}).get("content", "")
            # Evitamos que se muerda la cola clonando el mensaje actual
            if query_usuario not in contenido:
                recuerdos_encontrados.append(f"- {tipo}: '{contenido}'")
                
        if recuerdos_encontrados:
            return "\n".join(recuerdos_encontrados)
    except Exception as e:
        print(f"Error buscando en carpetas: {e}")
    return None

# ==========================================
# 4. PROMPT DE MEI
# ==========================================
mei_prompt = """
Eres Mei, un personaje complejo de una novela visual interactiva de rolplay basada en un matrimonio arreglado.

### Reglas Críticas de Formato Narrativo (Estilo Emochi)
1. No utilices formatos de código, ni viñetas, ni asteriscos en tu salida de texto.
2. Divide tu respuesta obligatoriamente en párrafos independientes. Cada párrafo debe ser o bien exclusivamente narrativo (en tercera persona, itálicas, detallando acciones y ambiente) o bien exclusivamente un diálogo (entre comillas dobles, primera persona, directo).

### Guía de Evolución Emocional
- FASE DE ODIO Y RESENTIMIENTO: Hostil, cortante, desconfiada, usa sarcasmo.
- FASE DE NEGOCIACIÓN: Calculadora, desafiante. Analiza la situación.
- FASE DE TEMOR Y CONFUSIÓN: Se muestra vulnerable pero intenta ocultarlo al notar que no eres cruel.
- FASE DE DIVERSIÓN Y COMPLICIDAD: Rebelde pero con chispas de desafío divertido o ironía.
- FASE DE AMOR PROFUNDO: Entrega su lealtad y devoción, intensa y dramática.
- FASE DE INTIMIDAD EXPLÍCITA: Entrega pasional salvaje, cruda y sin ningún tipo de censura.
"""

# ==========================================
# 5. PARSER DE TEXTO A BLOQUES VISUALES
# ==========================================
def renderizar_bloque_emochi(texto):
    parrafos = [p.strip() for p in texto.split('\n') if p.strip()]
    for parrafo in parrafos:
        if parrafo.startswith('"') or (parrafo.count('"') >= 2):
            st.markdown(f'<div class="emochi-container"><p class="dialogo"><span class="audio-indicator">🔊</span>{parrafo}</p></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="emochi-container"><p class="narracion"><span class="audio-indicator">🔊</span><i>{parrafo}</i></p></div>', unsafe_allow_html=True)

# ==========================================
# 6. INTERFAZ DE USUARIO Y LÓGICA DE TURNOS
# ==========================================
st.title("Mei — Matrimonio Arreglado")
st.markdown('<p class="caption-style">Beta v0.3 — Memoria Indexada por Carpetas</p>', unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Estado de la Novela")
    h, m = st.session_state.hora_juego
    st.subheader(f"⏰ Tiempo Interno: {h:02d}:{m:02d}")
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
    horas, minutos = st.session_state.hora_juego
    minutos += 15
    if minutos >= 60:
        horas += 1
        minutos = minutos % 60
    st.session_state.hora_juego = (horas % 24, minutos)

    # ACCIÓN DE LAS CARPETAS: Buscar recuerdos del pasado en MongoDB basados en el input actual
    recuerdos_contexto = buscar_recuerdos_en_carpetas(input_usuario)

    # Memoria de corto plazo (últimos 6 mensajes para el hilo de conversación inmediato)
    mensajes_recientes = mensajes_anteriores[-6:] if len(mensajes_anteriores) > 6 else mensajes_anteriores

    contents = []
    for msg in mensajes_recientes:
        if isinstance(msg, HumanMessage):
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=msg.content)]))
        elif isinstance(msg, AIMessage):
            contents.append(types.Content(role="model", parts=[types.Part.from_text(text=msg.content)]))
    
    # Construimos el inyector del mensaje actual incluyendo la hora y los recuerdos recuperados de las carpetas
    inyector_datos = f"\n\n[Contexto de Entorno: Reloj del juego a las {st.session_state.hora_juego[0]:02d}:{st.session_state.hora_juego[1]:02d}]"
    
    if recuerdos_contexto:
        inyector_datos += f"\n[CARPETA DE RECUERDOS EXTRAÍDOS DE MONGODB (Usa esta información si el usuario te está preguntando o haciendo referencia al pasado):\n{recuerdos_contexto}]"

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

            # Renderizado estético
            renderizar_bloque_emochi(respuesta_mei)

            # Guardar en el historial completo de MongoDB
            history.add_user_message(input_usuario)
            history.add_ai_message(respuesta_mei)
            
            st.rerun()

        except Exception as e:
            st.error(f"Error en el sistema de la API: {e}")
