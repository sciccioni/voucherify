import streamlit as st
import requests
from langchain_openai import ChatOpenAI
from langchain.agents import initialize_agent, Tool
from langchain.agents import AgentType

# --- 1. CONFIGURAZIONE CHIAVI ---
try:
    V_ID = st.secrets["VOUCHERIFY_APP_ID"]
    V_KEY = st.secrets["VOUCHERIFY_SECRET_KEY"]
    O_KEY = st.secrets["OPENAI_API_KEY"]
except Exception as e:
    st.error(f"⚠️ Errore Secrets: {e}")
    st.stop()

# Configurazione Header per Voucherify
HEADERS = {
    "X-App-Id": V_ID,
    "X-App-Token": V_KEY,
    "Content-Type": "application/json"
}
BASE_URL = "https://api.voucherify.io/v1"

# --- 2. FUNZIONI API (I NOSTRI TOOL) ---
def get_campaign_info(campaign_name):
    """Chiama direttamente l'API di Voucherify per una campagna."""
    try:
        name = str(campaign_name).strip().replace("'", "").replace('"', "")
        url = f"{BASE_URL}/campaigns/{name}"
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            return str(response.json())
        else:
            return f"Errore Voucherify: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Errore connessione: {str(e)}"

def list_campaigns(_=None):
    """Elenca le campagne tramite API."""
    try:
        url = f"{BASE_URL}/campaigns?limit=10"
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            return str(response.json())
        return f"Errore: {response.status_code}"
    except Exception as e:
        return f"Errore: {str(e)}"

tools = [
    Tool(
        name="Dettagli_Campagna",
        func=get_campaign_info,
        description="Ottiene info su una singola campagna. Passa solo il nome della campagna."
    ),
    Tool(
        name="Lista_Campagne",
        func=list_campaigns,
        description="Mostra le ultime campagne create."
    )
]

# --- 3. INTERFACCIA ---
st.set_page_config(page_title="Voucherify AI Agent", page_icon="🎫")
st.title("🎫 Voucherify AI Agent (Direct API)")

if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

if prompt := st.chat_input("Chiedimi info sulle campagne..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            llm = ChatOpenAI(model="gpt-4o", openai_api_key=O_KEY, temperature=0)
            agent = initialize_agent(
                tools, llm, 
                agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, 
                verbose=True,
                handle_parsing_errors=True
            )
            
            with st.spinner("Interrogando Voucherify via REST API..."):
                response = agent.run(prompt)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
        except Exception as e:
            st.error(f"Errore: {e}")
