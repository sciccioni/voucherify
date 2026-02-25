import streamlit as st
from voucherify_python_sdk import Voucherify
from langchain_openai import ChatOpenAI
from langchain.agents import initialize_agent, Tool
from langchain.agents import AgentType

# --- RECUPERO CREDENZIALI (Da Streamlit Secrets o .env) ---
# Se provi in locale, usa st.secrets o un file .env
V_APP_ID = st.secrets["VOUCHERIFY_APP_ID"]
V_SECRET_KEY = st.secrets["VOUCHERIFY_SECRET_KEY"]
O_API_KEY = st.secrets["OPENAI_API_KEY"]

# Inizializza Voucherify
client = Voucherify(V_APP_ID, V_SECRET_KEY)

# --- DEFINIZIONE TOOL ---
def get_campaign(name):
    """Ottiene i dettagli di una campagna specifica su Voucherify."""
    try:
        return str(client.campaigns.get(name))
    except Exception as e:
        return f"Errore: {e}"

def list_campaigns(limit=10):
    """Mostra la lista delle ultime campagne create."""
    try:
        return str(client.campaigns.list({"limit": limit}))
    except Exception as e:
        return f"Errore: {e}"

tools = [
    Tool(name="Info_Campagna", func=get_campaign, description="Cerca dettagli di una singola campagna tramite nome"),
    Tool(name="Lista_Campagne", func=list_campaigns, description="Elenca le campagne attive sul sistema")
]

# --- INTERFACCIA UI ---
st.set_page_config(page_title="Voucherify AI", layout="centered")
st.title("🎫 Voucherify AI Agent")

if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

if prompt := st.chat_input("Chiedimi: 'Quali sono le campagne attive?'"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        llm = ChatOpenAI(model="gpt-4o", openai_api_key=O_API_KEY, temperature=0)
        agent = initialize_agent(tools, llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, verbose=True)
        
        response = agent.run(prompt)
        st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})