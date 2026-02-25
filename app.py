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
    url = f"{BASE_URL}/campaigns?limit=20"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else f"Errore: {res.text}"

# --- AGENTE ---
def run_conversation(user_prompt, chat_history):
    system_prompt = """Sei un assistente di supporto clienti per PhotoSì, esperto delle campagne promozionali Voucherify.

Quando recuperi i dati di una campagna, rispondi SEMPRE in questo formato esatto:

📅 Quando posso richiedere il codice promo?
Dal [start_date] al [expiration_date] (con validità dei codici fino al [voucher_validity])

🎁 Cosa prevede la promo?
[percentuale o valore sconto] su ordine minimo [min_order_amount] euro, [info spese spedizione], [cumulabilità con altre promo]

🛍️ Per quali prodotti è valido il codice?
[lista prodotti o "tutti i prodotti"]

📱 Posso ordinare sia da app che dal sito?
Sì / No / [specifica se solo app o solo sito]

🔁 Quante volte posso usare il codice?
[numero utilizzi, es. "Il codice è valido per un solo utilizzo sia sull'app che sul sito PhotoSì"]

⏳ Entro quanto è valido il codice?
Il codice sarà valido entro il [voucher_expiry_date]

---
Regole:
- Usa SEMPRE get_campaign_info per recuperare i dati prima di rispondere
- Se l'utente non conosce il nome esatto della campagna, usa list_campaigns e mostragli l'elenco con i nomi
- NON mostrare mai JSON grezzo
- Se un'informazione non è disponibile nei dati, scrivi "Non specificato"
- Rispondi sempre in italiano
- Le date formattale sempre come: GG mese AAAA (es. 19 agosto 2024)
- Se la campagna è scaduta, segnalalo con ⚠️ in cima alla risposta"""

    # Costruisce i messaggi includendo la cronologia
    messages = [{"role": "system", "content": system_prompt}]
    
    # Aggiunge la storia della chat (escludi l'ultimo messaggio utente, lo aggiungiamo dopo)
    for msg in chat_history[:-1]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    
    # Aggiunge il messaggio corrente
    messages.append({"role": "user", "content": user_prompt})

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_campaign_info",
                "description": "Ottieni tutti i dettagli di una campagna specifica da Voucherify tramite il suo nome o ID",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Il nome esatto o ID della campagna"
                        }
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_campaigns",
                "description": "Elenca tutte le campagne disponibili su Voucherify",
                "parameters": {
                    "type": "object",
                    "properties": {}
                },
            },
        }
    ]

    # Prima chiamata
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
            elif function_name == "list_campaigns":
                result = list_campaigns()
            else:
                result = {"error": "Funzione non trovata"}

            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": json.dumps(result, ensure_ascii=False),
            })

        # Seconda chiamata con i risultati dei tool
        second_response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
        )
        return second_response.choices[0].message.content

    return response_message.content


# --- INTERFACCIA STREAMLIT ---
st.set_page_config(page_title="Voucherify Agent", page_icon="🎫", layout="centered")
st.title("🎫 PhotoSì - Voucherify Agent")
st.caption("Chiedimi info su qualsiasi campagna promozionale")

# Inizializza la cronologia
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Mostra la cronologia
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Input utente
if prompt := st.chat_input("Es: Dimmi tutto sulla campagna SUMMER2024..."):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Interrogando Voucherify..."):
            answer = run_conversation(prompt, st.session_state.chat_history)
            st.markdown(answer)
            st.session_state.chat_history.append({"role": "assistant", "content": answer})
```

E il `requirements.txt`:
```
streamlit
openai
requests
