import streamlit as st
from voucherify.client import Client
from langchain_openai import ChatOpenAI
from langchain.agents import initialize_agent, Tool
from langchain.agents import AgentType

# --- 1. CONFIGURAZIONE CREDENZIALI ---
# Assicurati di averle inserite nei "Secrets" di Streamlit
try:
    V_APP_ID = st.secrets["VOUCHERIFY_APP_ID"]
    V_SECRET_KEY = st.secrets["VOUCHERIFY_SECRET_KEY"]
    O_API_KEY = st.secrets["OPENAI_API_KEY"]
except KeyError:
    st.error("ERRORE: Chiavi mancanti nei Secrets di Streamlit! Controlla le impostazioni.")
    st.stop()

# Inizializzazione Client Voucherify (Versione 3.x)
voucherify_client = Client(
    app_id=V_APP_ID,
    secret_key=V_SECRET_KEY
)

# --- 2. DEFINIZIONE TOOL PER L'AGENTE ---
def get_campaign_info(campaign_name):
    """Ottiene i dettagli tecnici di una campagna."""
    try:
        # Pulisce la stringa dal nome della campagna
        name = campaign_name.strip()
        res = voucherify_client.campaigns.get(name)
        return str(res)
    except Exception as e:
        return f"Campagna non trovata o errore: {str(e)}"

def list_all_campaigns(dummy_arg=None):
    """Elenca le ultime 10 campagne create."""
    try:
        res = voucherify_client.campaigns.list({"limit": 10})
        return str(res)
    except Exception as e:
        return f"Errore nel recupero della lista: {str(e)}"

tools = [
    Tool(
        name="DettagliCampagna",
        func=get_campaign_info,
        description="Utile quando l'utente chiede informazioni su una specifica campagna fornendo il nome."
    ),
    Tool(
        name="ListaCampagne",
        func=list_all_campaigns,
        description="Utile per vedere quali campagne sono attive o presenti nel sistema."
    )
]

# --- 3. INTERFACCIA CHAT STREAMLIT ---
st.set_page_config(page_title="Voucherify AI Agent", page_icon="🎫")
st.title("🎫 Voucherify AI Agent")
st.info("Chiedimi info sulle tue campagne Voucherify (Sandbox).")

# Inizializzazione memoria chat
if "messages" not in st.session_state:
    st.session_state.messages = []

# Mostra messaggi precedenti
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Input utente
if prompt := st.chat_input("Esempio: 'Quali campagne ho?' oppure 'Dettagli per SUMMER_2025'"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Esecuzione dell'Agente AI
    with st.chat_message("assistant"):
        try:
            llm = ChatOpenAI(
                model="gpt-4o", 
                openai_api_key=O_API_KEY, 
                temperature=0
            )
            
            agent = initialize_agent(
                tools, 
                llm, 
                agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, 
                verbose=True,
                handle_parsing_errors=True
            )
            
            with st.spinner("Interrogando Voucherify..."):
                full_response = agent.run(prompt)
                st.markdown(full_response)
                st.session_state.messages.append({"role": "assistant", "content": full_response})
        except Exception as e:
            st.error(f"Errore durante l'elaborazione: {str(e)}")
