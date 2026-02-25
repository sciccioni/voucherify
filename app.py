import streamlit as st
from voucherify.client import Client # Import corretto per il pacchetto 'voucherify'
from langchain_openai import ChatOpenAI
from langchain.agents import initialize_agent, Tool
from langchain.agents import AgentType

# --- 1. CONFIGURAZIONE ---
try:
    v_id = st.secrets["VOUCHERIFY_APP_ID"]
    v_key = st.secrets["VOUCHERIFY_SECRET_KEY"]
    o_key = st.secrets["OPENAI_API_KEY"]
except Exception as e:
    st.error(f"⚠️ Errore nei Secrets: {e}")
    st.stop()

# Inizializzazione Client
# La classe Client si aspetta app_id e secret_key
v_client = Client(app_id=v_id, secret_key=v_key)

# --- 2. TOOLS ---
def get_campaign_tool(name):
    try:
        # Pulisce l'input dell'AI
        clean_name = str(name).strip().replace("'", "").replace('"', "")
        res = v_client.campaigns.get(clean_name)
        return f"Dati della campagna {clean_name}: {res}"
    except Exception as e:
        return f"Errore nel recupero della campagna: {str(e)}"

def list_campaigns_tool(_=None):
    try:
        res = v_client.campaigns.list({"limit": 5})
        return f"Ultime campagne: {res}"
    except Exception as e:
        return f"Errore nella lista: {str(e)}"

tools = [
    Tool(
        name="Dettagli_Campagna",
        func=get_campaign_tool,
        description="Usa questo per ottenere info su una singola campagna. Fornisci il nome come input."
    ),
    Tool(
        name="Elenco_Campagne",
        func=list_campaigns_tool,
        description="Usa questo per vedere la lista delle campagne disponibili."
    )
]

# --- 3. INTERFACCIA ---
st.title("🎫 Voucherify AI Agent")

if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

if prompt := st.chat_input("Chiedimi qualcosa sulle tue campagne..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        llm = ChatOpenAI(model="gpt-4o", openai_api_key=o_key, temperature=0)
        agent = initialize_agent(
            tools, llm, 
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, 
            verbose=True,
            handle_parsing_errors=True
        )
        
        with st.spinner("Sto consultando Voucherify..."):
            try:
                response = agent.run(prompt)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                st.error(f"Errore durante l'elaborazione: {e}")
