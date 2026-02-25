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
    if res.status_code != 200:
        return f"Errore: {res.text}"
    
    data = res.json()
    
    # Estrai il campo redemption limit in modo esplicito
    redemption_info = {}
    
    # Cerca in validation_rules_assignments
    val_rules_url = f"{BASE_URL}/campaigns/{name.strip()}/validation-rules-assignments"
    val_res = requests.get(val_rules_url, headers=HEADERS)
    if val_res.status_code == 200:
        redemption_info["validation_rules"] = val_res.json()
    
    # Cerca il limite direttamente nella campagna
    voucher = data.get("voucher", {})
    redemption = voucher.get("redemption", {})
    campaign_redemption = data.get("redemption", {})
    
    # Aggiungi info esplicite al dato restituito
    data["_parsed_redemption"] = {
        "quantity": data.get("vouchers_count"),
        "per_customer_limit": redemption.get("quantity") or campaign_redemption.get("quantity"),
        "redeemed_quantity": redemption.get("redeemed_quantity") or campaign_redemption.get("redeemed_quantity"),
        "validation_rules_raw": redemption_info.get("validation_rules", {})
    }
    
    return data

def get_campaign_validation_rules(name):
    """Recupera le validation rules di una campagna per trovare limiti per customer"""
    url = f"{BASE_URL}/campaigns/{name.strip()}/validation-rules-assignments"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        return f"Errore: {res.text}"
    
    data = res.json()
    
    # Ora recupera il dettaglio di ogni validation rule
    rules_detail = []
    for item in data.get("data", []):
        rule_id = item.get("rule_id")
        if rule_id:
            rule_url = f"{BASE_URL}/validation-rules/{rule_id}"
            rule_res = requests.get(rule_url, headers=HEADERS)
            if rule_res.status_code == 200:
                rules_detail.append(rule_res.json())
    
    return {
        "assignments": data,
        "rules_detail": rules_detail
    }

def list_campaigns():
    url = f"{BASE_URL}/campaigns?limit=20"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else f"Errore: {res.text}"

# --- AGENTE ---
def run_conversation(user_prompt, chat_history):
    system_prompt = """Sei un assistente di supporto clienti per PhotoSì, esperto delle campagne promozionali Voucherify.

Quando recuperi i dati di una campagna, chiama SEMPRE sia get_campaign_info che get_campaign_validation_rules per avere tutti i dati completi.

Rispondi SEMPRE in questo formato esatto:

📅 Quando posso richiedere il codice promo?
Dal [start_date] al [expiration_date] (con validità dei codici fino al [voucher_validity])

🎁 Cosa prevede la promo?
[percentuale o valore sconto] su ordine minimo [min_order_amount] euro, [info spese spedizione], [cumulabilità con altre promo]

🛍️ Per quali prodotti è valido il codice?
[lista prodotti o "tutti i prodotti"]

📱 Posso ordinare sia da app che dal sito?
Sì / No / [specifica se solo app o solo sito]

🔁 Quante volte posso usare il codice?
[Cerca questo valore in questo ordine di priorità:]
1. Nelle validation_rules_detail: cerca campi come "redemptions_per_customer", "per_customer", "customer_rules" o simili con un valore numerico
2. Nel campo _parsed_redemption.per_customer_limit
3. Nel campo voucher.redemption.quantity
Se trovi un valore numerico (es. 3), scrivi: "Il codice può essere utilizzato massimo [N] volte per cliente"
Se non trovi nulla, scrivi: "Non specificato"

⏳ Entro quanto è valido il codice?
Il codice sarà valido entro il [voucher_expiry_date]

---
Regole importanti:
- Chiama SEMPRE get_campaign_validation_rules oltre a get_campaign_info
- Nelle validation rules cerca QUALSIASI campo che contenga "redemption", "per_customer", "customer", "limit", "quantity" con valore numerico
- NON mostrare mai JSON grezzo
- Se un'informazione non è disponibile, scrivi "Non specificato"
- Rispondi sempre in italiano
- Le date formattale sempre come: GG mese AAAA (es. 19 agosto 2024)
- Se la campagna è scaduta, segnalalo con ⚠️ in cima alla risposta"""

    messages = [{"role": "system", "content": system_prompt}]
    
    for msg in chat_history[:-1]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    
    messages.append({"role": "user", "content": user_prompt})

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_campaign_info",
                "description": "Ottieni tutti i dettagli di una campagna specifica da Voucherify",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Nome o ID della campagna"}
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_campaign_validation_rules",
                "description": "Recupera le validation rules di una campagna, inclusi i limiti di utilizzo per cliente (redemptions per customer per incentive)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Nome o ID della campagna"}
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
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    # Loop agente per gestire multiple tool calls
    max_iterations = 5
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls

        if not tool_calls:
            return response_message.content

        messages.append(response_message)

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)

            if function_name == "get_campaign_info":
                result = get_campaign_info(args.get("name"))
            elif function_name == "get_campaign_validation_rules":
                result = get_campaign_validation_rules(args.get("name"))
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

    return "Non sono riuscito a recuperare le informazioni. Riprova."


# --- INTERFACCIA STREAMLIT ---
st.set_page_config(page_title="Voucherify Agent", page_icon="🎫", layout="centered")
st.title("🎫 PhotoSì - Voucherify Agent")
st.caption("Chiedimi info su qualsiasi campagna promozionale")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Es: Dimmi tutto sulla campagna COMARKETING_TUM_SETT2025_3..."):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Interrogando Voucherify..."):
            answer = run_conversation(prompt, st.session_state.chat_history)
            st.markdown(answer)
            st.session_state.chat_history.append({"role": "assistant", "content": answer})
