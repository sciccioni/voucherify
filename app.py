import streamlit as st
import requests
import json
from openai import OpenAI

# ---------------------------------------------------------------------------
# CONFIGURAZIONE
# ---------------------------------------------------------------------------
try:
    V_ID = st.secrets["VOUCHERIFY_APP_ID"]
    V_KEY = st.secrets["VOUCHERIFY_SECRET_KEY"]
    O_KEY = st.secrets["OPENAI_API_KEY"]
except Exception:
    st.error("⚠️ Mancano le chiavi nei Secrets di Streamlit! Configura VOUCHERIFY_APP_ID, VOUCHERIFY_SECRET_KEY e OPENAI_API_KEY.")
    st.stop()

client = OpenAI(api_key=O_KEY)

HEADERS = {
    "X-App-Id": V_ID,
    "X-App-Token": V_KEY,
    "Content-Type": "application/json",
}
BASE_URL = "https://api.voucherify.io/v1"

# ---------------------------------------------------------------------------
# HELPER: chiamata API con gestione errori centralizzata
# ---------------------------------------------------------------------------
def _get(url: str) -> dict:
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            return res.json()
        return {"error": f"HTTP {res.status_code}", "detail": res.text}
    except requests.exceptions.RequestException as e:
        return {"error": "Errore di rete", "detail": str(e)}

def _post(url: str, payload: dict) -> dict:
    try:
        res = requests.post(url, headers=HEADERS, json=payload, timeout=10)
        if res.status_code == 200:
            return res.json()
        return {"error": f"HTTP {res.status_code}", "detail": res.text}
    except requests.exceptions.RequestException as e:
        return {"error": "Errore di rete", "detail": str(e)}

# ---------------------------------------------------------------------------
# FUNZIONI VOUCHERIFY (TOOLS)
# ---------------------------------------------------------------------------

def list_campaigns(limit: int = 100) -> dict:
    """Recupera una lista delle ultime campagne create. Ritorna nome, date e stato."""
    data = _get(f"{BASE_URL}/campaigns?limit={limit}")
    if "error" in data:
        return data
    
    # Semplifichiamo l'output per non consumare troppi token
    simplified = []
    for c in data.get("campaigns", []):
        simplified.append({
            "name": c.get("name"),
            "active": c.get("active"),
            "start_date": c.get("start_date"),
            "expiration_date": c.get("expiration_date"),
            "created_at": c.get("created_at")
        })
    return {"campaigns": simplified}

def get_voucher_info(code: str) -> dict:
    """Dati del singolo codice voucher (stato, campagna, metadata)."""
    return _get(f"{BASE_URL}/vouchers/{code.strip()}")

def get_campaign_info(name: str) -> dict:
    """Dati generali della campagna (date, sconto, stato)."""
    return _get(f"{BASE_URL}/campaigns/{name.strip()}")

def get_campaign_validation_rules(name: str) -> dict:
    """Analisi delle regole di validazione per trovare il limite per cliente."""
    data = _get(f"{BASE_URL}/campaigns/{name.strip()}")
    if "error" in data:
        return data

    assignments = data.get("validation_rules_assignments", {}).get("data", [])
    per_customer_limit = None

    for item in assignments:
        rid = item.get("rule_id")
        if rid:
            rule = _get(f"{BASE_URL}/validation-rules/{rid}")
            if "error" not in rule:
                for _, r_val in rule.get("rules", {}).items():
                    if isinstance(r_val, dict) and r_val.get("name") == "redemption.count.per_customer":
                        per_customer_limit = r_val.get("conditions", {}).get("$less_than_or_equal", [None])[0]

    if per_customer_limit is None:
        per_customer_limit = data.get("voucher", {}).get("redemption", {}).get("quantity")

    return {"per_customer_limit": per_customer_limit}

def get_campaign_redemptions(name: str, max_pages: int = 5) -> dict:
    """Statistiche redemptions con paginazione (fino a max_pages * 100 risultati)."""
    campaign_name = name.strip()
    successful = 0
    failed = 0
    total_fetched = 0
    page = 1

    params_base = f"campaign_name={requests.utils.quote(campaign_name)}&limit=100"

    for _ in range(max_pages):
        url = f"{BASE_URL}/redemptions?{params_base}&page={page}"
        data = _get(url)
        if "error" in data:
            return data

        reds = data.get("redemptions", [])
        if not reds:
            break

        camp_reds = [r for r in reds if r.get("voucher", {}).get("campaign") == campaign_name]
        successful += len([r for r in camp_reds if r.get("result") == "SUCCESS" and r.get("status") == "SUCCEEDED"])
        failed += len([r for r in camp_reds if r.get("result") == "FAILURE"])
        total_fetched += len(camp_reds)

        if len(reds) < 100:
            break
        page += 1

    return {
        "successful": successful,
        "failed": failed,
        "total_fetched": total_fetched,
        "note": f"Analizzate fino a {max_pages * 100} redemptions recenti.",
    }

def get_campaign_vouchers(name: str) -> dict:
    """Conteggio totale voucher generati nella campagna."""
    data = _get(f"{BASE_URL}/campaigns/{name.strip()}/vouchers?limit=1")
    if "error" in data:
        return data
    return {"total_vouchers": data.get("total", 0)}

def validate_voucher_simulation(code: str, customer_email: str, order_amount: float) -> dict:
    """Simula una validazione carrello per troubleshooting."""
    payload = {
        "customer": {"source_id": customer_email.strip()},
        "order": {"amount": int(float(order_amount) * 100)},
        "voucher": code.strip(),
    }
    return _post(f"{BASE_URL}/redemptions/validate", payload)

def debug_campaign_json(name: str) -> dict:
    """Recupera il JSON grezzo della campagna (per sidebar debug)."""
    return _get(f"{BASE_URL}/campaigns/{name.strip()}")

# ---------------------------------------------------------------------------
# DEFINIZIONE TOOLS PER OPENAI
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_campaigns",
            "description": "Restituisce una lista delle campagne recenti (nome, date, stato). Usalo quando l'utente chiede quali campagne ci sono in un certo periodo (es. 'campagne di febbraio').",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_voucher_info",
            "description": "Dati del singolo codice voucher per scoprire a quale campagna appartiene.",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string", "description": "Il codice voucher da analizzare."}},
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_campaign_info",
            "description": "Dati generali della campagna (date, sconto, stato attivo/scaduto).",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Nome esatto della campagna."}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_campaign_validation_rules",
            "description": "Analizza le regole di validazione per trovare il limite di utilizzo per cliente.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Nome esatto della campagna."}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_campaign_redemptions",
            "description": "Statistiche di redemption della campagna (successi e fallimenti).",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Nome esatto della campagna."}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_campaign_vouchers",
            "description": "Restituisce il conteggio totale di voucher generati nella campagna.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Nome esatto della campagna."}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_voucher_simulation",
            "description": "Simula la validazione di un voucher su un carrello specifico per troubleshooting.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Il codice voucher da simulare."},
                    "customer_email": {"type": "string", "description": "Email o source_id del cliente."},
                    "order_amount": {"type": "number", "description": "Importo dell'ordine in euro."},
                },
                "required": ["code", "customer_email", "order_amount"],
            },
        },
    },
]

TOOL_MAP = {
    "list_campaigns": list_campaigns,
    "get_voucher_info": get_voucher_info,
    "get_campaign_info": get_campaign_info,
    "get_campaign_validation_rules": get_campaign_validation_rules,
    "get_campaign_redemptions": get_campaign_redemptions,
    "get_campaign_vouchers": get_campaign_vouchers,
    "validate_voucher_simulation": validate_voucher_simulation,
}

# ---------------------------------------------------------------------------
# SISTEMA PROMPT
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """Sei l'assistente PhotoSì esperto di Voucherify. Segui sempre i dati reali restituiti dalle API.

SCENARIO 1: L'UTENTE CHIEDE UNA LISTA DI CAMPAGNE (es. "Campagne attive a febbraio")
- Usa il tool `list_campaigns` per recuperare le campagne.
- Filtra mentalmente i risultati incrociando lo stato 'active' e le date richieste (start_date, expiration_date o created_at) col mese richiesto.
- Rispondi fornendo un elenco puntato chiaro e leggibile delle campagne pertinenti.

SCENARIO 2: L'UTENTE INSERISCE UN CODICE PROMO O IL NOME DI UNA CAMPAGNA
1. Se ha inserito un CODICE (es. 4XP2K0ZX), chiama PRIMA `get_voucher_info(code)` per scoprire il nome della campagna di appartenenza.
2. Una volta che hai il NOME DELLA CAMPAGNA (o se l'utente ti ha scritto direttamente il nome), chiama TUTTI i seguenti tool con il NOME della campagna:
   - get_campaign_info
   - get_campaign_validation_rules
   - get_campaign_redemptions
   - get_campaign_vouchers
   (Non chiamarli passandogli il codice, ma il nome della campagna!).
   
3. Rispondi all'utente dicendo a quale campagna appartiene il codice (se ha fornito un codice) e mostra SEMPRE questo FORMATO RISPOSTA OBBLIGATORIO:

📅 **Periodo validità**
Dal [created_at] al [expiration_date]

🎁 **Cosa prevede la promo?**
[Sconto] su ordine minimo [min_amount]

🛍️ **Per quali prodotti è valido?**
[metadata.longDescription.IT o descrizione disponibile]

📱 **Canali di utilizzo**
Sia da app che dal sito PhotoSì.

🔁 **Quante volte posso usare il codice?**
[per_customer_limit dalla regola di validazione]

📊 **Stato della campagna**
- Nome Campagna: [Nome della campagna]
- Stato: [Attiva ✅ / Scaduta ⚠️ / Disabilitata ❌]
- Codici totali generati: [total_vouchers]
- Redemptions riuscite: [successful]
- Redemptions fallite: [failed]

🌍 **Lingue disponibili**
[Elenco lingue dai metadata, se presenti]

Se una chiamata restituisce errore, ignorala e usa i dati delle altre. Non inventare mai informazioni non presenti nei dati."""

# ---------------------------------------------------------------------------
# AGENTE CONVERSAZIONALE
# ---------------------------------------------------------------------------
def run_conversation(user_prompt: str, chat_history: list) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for msg in chat_history[:-1]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_prompt})

    max_iterations = 10
    for iteration in range(max_iterations):
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            return msg.content or "Non ho ricevuto una risposta dall'API."

        messages.append(msg)
        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}

            fn = TOOL_MAP.get(fn_name)
            if fn is None:
                result = {"error": f"Tool '{fn_name}' non trovato."}
            else:
                try:
                    result = fn(**args)
                except Exception as e:
                    result = {"error": f"Errore durante l'esecuzione: {str(e)}"}

            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": fn_name,
                "content": json.dumps(result, ensure_ascii=False),
            })

    return "⚠️ Numero massimo di iterazioni raggiunto. Riprova con una richiesta più specifica."

# ---------------------------------------------------------------------------
# INTERFACCIA STREAMLIT
# ---------------------------------------------------------------------------
st.set_page_config(page_title="PhotoSì Voucherify Agent", page_icon="🎫", layout="wide")
st.title("🎫 PhotoSì — Voucherify Pro Agent")
st.caption("Analizza voucher e campagne Voucherify in linguaggio naturale.")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Chiedimi di un voucher, una campagna o le promo attive in un mese..."):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Sto interrogando Voucherify..."):
            answer = run_conversation(prompt, st.session_state.chat_history)
        st.markdown(answer)
        st.session_state.chat_history.append({"role": "assistant", "content": answer})

# ---------------------------------------------------------------------------
# SIDEBAR: Debug JSON
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("🔧 Debug JSON")
    st.caption("Ispeziona il JSON grezzo di una campagna.")

    debug_name = st.text_input("Nome campagna", placeholder="es. SUMMER_2024")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📥 Carica JSON", use_container_width=True) and debug_name:
            with st.spinner("Caricamento..."):
                result = debug_campaign_json(debug_name)
            st.session_state["debug_json"] = result

    with col2:
        if st.button("🗑️ Pulisci", use_container_width=True):
            st.session_state.pop("debug_json", None)

    if "debug_json" in st.session_state:
        data = st.session_state["debug_json"]
        if "error" in data:
            st.error(f"Errore: {data['error']}")
        else:
            st.success(f"✅ Campagna: {data.get('name', 'N/A')}")
            status = data.get("active", False)
            st.metric("Stato", "🟢 Attiva" if status else "🔴 Inattiva")
            st.metric("Vouchers totali", data.get("vouchers_count", "N/A"))
            st.divider()
            st.json(data)

    st.divider()
    st.caption("PhotoSì © 2024 — Voucherify Agent")
