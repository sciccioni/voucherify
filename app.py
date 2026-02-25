import streamlit as st
from voucherify.client import Client
from langchain_openai import ChatOpenAI
from langchain.agents import initialize_agent, Tool
from langchain.agents import AgentType

# --- CONFIGURAZIONE ---
# Assicurati che questi nomi siano IDENTICI nei Secrets di Streamlit
try:
    v_id = st.secrets["VOUCHERIFY_APP_ID"]
    v_key = st.secrets["VOUCHERIFY_SECRET_KEY"]
    o_key = st.secrets["OPENAI_API_KEY"]
except Exception as e:
    st.error(f"⚠️ Errore Secrets: {e}. Controlla i nomi su Streamlit Cloud!")
    st.stop()

# Inizializza Voucherify
v_client = Client(app_id=v_id, secret_key=v_key)

# --- TOOLS ---
def get_campaign(name):
    try:
        # L'agente a volte passa stringhe sporche, puliamole
        clean_name = name.strip().replace("'", "").replace('"', "")
        res = v_client.campaigns.get(clean_name)
        return str(res)
    except Exception as e:
        return f"Errore: Campagna '{name}' non trovata. Dettaglio: {e}"

def list_campaigns(_=None):
    try:
        res = v_client.campaigns.list({"limit": 5})
        return str(res)
    except Exception as e:
        return f"Errore lista: {e}"

tools = [
    Tool(name="Info_Campagna", func=get_campaign, description="Usa questo per dettagli su una singola campagna. Input: nome campagna"),
    Tool(name="Lista_Campagne", func=list_campaigns, description="Usa questo per vedere le ultime campagne.")
]

# --- UI ---
st.title("🎫 Voucherify AI Agent")

if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]): st.markdown(m["content"])

if prompt := st.chat_input("Cosa vuoi sapere?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)

    with st.chat_message("assistant"):
        llm = ChatOpenAI(model="gpt-4o", openai_api_key=o_key, temperature=0)
        agent = initialize_agent(
            tools, llm, 
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, 
            verbose=True,
            handle_parsing_errors=True # Fondamentale per non far crashare tutto
        )
        
        with st.spinner("Cerco su Voucherify..."):
            try:
                response = agent.run(prompt)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                st.error(f"Errore Agente: {e}")
