import streamlit as st
import requests
import json
from openai import OpenAI

# --- CONFIGURAZIONE ---
try:
    V_ID = st.secrets["VOUCHERIFY_APP_ID"]
    V_KEY = st.secrets["VOUCHERIFY_SECRET_KEY"]
    O_KEY = st.secrets["OPENAI_API_KEY"]
except Exception as e:
    st.error("Mancano le chiavi nei Secrets di Streamlit!")
    st.stop()

client = OpenAI(api_key=O_KEY)
HEADERS = {"X-App-Id": V_ID, "X-App-Token": V_KEY, "Content-Type": "application/json"}
BASE_URL = "https://api.voucherify.io/v1"

# --- FUNZIONI VOUCHERIFY ---
def get_campaign_info(name):
    url = f"{BASE_URL}/campaigns/{name.strip()}"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else f"Errore: {res.text}"

def list_campaigns():
    url = f"{BASE_URL}/campaigns?limit=10"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else f"Errore: {res.text}"

# --- LOGICA AGENTE (NATIVA) ---
def run_conversation(user_prompt):
    messages = [{"role": "user", "content": user_prompt}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_campaign_info",
                "description": "Ottieni dettagli di una campagna specifica",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_campaigns",
                "description": "Elenca le ultime campagne",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )
    
    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls

    if tool_calls:
        messages.append(response_message)
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            
            if function_name == "get_campaign_info":
                result = get_campaign_info(args.get("name"))
            else:
                result = list_campaigns()
                
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": json.dumps(result),
            })
        
        second_response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
        )
        return second_response.choices[0].message.content
    return response_message.content

# --- INTERFACCIA STREAMLIT ---
st.title("🎫 Voucherify Smart Agent")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]): st.markdown(msg["content"])

if prompt := st.chat_input("Chiedimi info sulle campagne..."):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)
    
    with st.chat_message("assistant"):
        with st.spinner("Interrogando Voucherify..."):
            answer = run_conversation(prompt)
            st.markdown(answer)
            st.session_state.chat_history.append({"role": "assistant", "content": answer})
