"""
Streamlit Web Demo for Autonomous Customer Support Agent.
Connects with FastAPI backend endpoints:
- GET /health
- POST /login
- GET /orders
- POST /chat
- POST /confirm
- GET /audit
"""
import json
import requests
import streamlit as st

API_BASE_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="Team Logic - AI Customer Support Agent",
    page_icon="🤖",
    layout="wide"
)

# Initialize Session State
if "token" not in st.session_state:
    st.session_state.token = "cust_1"
if "customer_email" not in st.session_state:
    st.session_state.customer_email = "alice@example.com"
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "pending_change_request" not in st.session_state:
    st.session_state.pending_change_request = None
if "queued_prompt" not in st.session_state:
    st.session_state.queued_prompt = None

# Dark, card-based styling (inspired by the Resolvo mock-up)
st.markdown(
    """
    <style>
    [data-testid="stSidebar"] { background:#1a1a1a; border-right:1px solid #2a2a2a; }
    .brand { font-size:1.6rem; font-weight:700; margin:0; }
    .brand-sub { color:#8a8a8a; font-size:.8rem; margin-bottom:1rem; }
    .hero { text-align:center; padding:3rem 0 1.5rem; }
    .hero .logo { width:72px; height:72px; margin:0 auto 1rem; border-radius:20px;
        background:linear-gradient(135deg,#0b3d91,#1d6bff); display:flex;
        align-items:center; justify-content:center; font-size:2rem; }
    .hero .hello { color:#8a8a8a; font-size:.9rem; }
    .hero h1 { font-size:2.4rem; font-weight:500; margin:.3rem 0 0; }
    div.stButton > button { background:#212121; border:1px solid #2f2f2f;
        border-radius:12px; color:#e8e8e8; text-align:left; }
    div.stButton > button:hover { border-color:#1d6bff; color:#fff; }
    div.stButton > button[kind="primary"] { background:#1d6bff; border-color:#1d6bff; }
    [data-testid="stChatInput"] { border-radius:16px; }
    [data-testid="stVerticalBlockBorderWrapper"] { background:#1e1e1e; border-radius:14px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# Helper API caller
def api_request(method: str, path: str, json_data: dict = None):
    url = f"{API_BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    try:
        if method.upper() == "GET":
            resp = requests.get(url, headers=headers, timeout=5)
        else:
            resp = requests.post(url, headers=headers, json=json_data, timeout=5)
        return resp.status_code, resp.json()
    except Exception as e:
        return 500, {"error": f"Cannot connect to FastAPI backend at {API_BASE_URL}. Is it running? Details: {str(e)}"}


# Sidebar: brand, navigation, session & backend status
with st.sidebar:
    st.markdown('<p class="brand">Team Logic</p><p class="brand-sub">AI-Powered Support</p>', unsafe_allow_html=True)

    page = st.radio("Navigate", ["💬 Ask Agent", "📦 Orders", "🛡️ Audit Log"], label_visibility="collapsed")

    st.markdown("---")
    st.caption("CUSTOMER SESSION")
    st.write("👤 Alice Smith")
    st.write(f"📧 `{st.session_state.customer_email}`")
    st.write(f"🔑 `{st.session_state.token}`")

    st.markdown("---")
    st.caption("BACKEND STATUS")
    status_code, health = api_request("GET", "/health")
    if status_code == 200:
        st.success(f"FastAPI Online (v{health.get('version', '1.0')})")
    else:
        st.warning("FastAPI Offline. Start backend with `uvicorn main:app --reload`")

    st.markdown("---")
    if st.button("🗑️ Clear Conversation", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.pending_change_request = None
        st.rerun()


# ============================================================================
# PAGE 1: Chat & Guardrails
# ============================================================================
SUGGESTIONS = [
    ("📍", "Change Address", "Change shipping address for order 10023 to 12 MG Road, Pune"),
    ("🚚", "Track Order", "Track order 10023"),
    ("❌", "Cancel Order", "Cancel order 10023"),
    ("🛡️", "Try a Blocked Change", "Change shipping address for order 10024 to 55 Lake Road"),
]

if page == "💬 Ask Agent":
    # Welcome hero + suggestion cards, shown only on an empty conversation
    if not st.session_state.chat_history and not st.session_state.pending_change_request:
        st.markdown(
            '<div class="hero"><div class="logo">✦</div>'
            '<div class="hello">Hello! Alice Smith</div>'
            '<h1>How can I help you today?</h1></div>',
            unsafe_allow_html=True,
        )
        cols = st.columns(len(SUGGESTIONS))
        for col, (icon, title, prompt) in zip(cols, SUGGESTIONS):
            with col:
                if st.button(f"{icon}\n\n{title}", key=f"sug_{title}", use_container_width=True):
                    st.session_state.queued_prompt = prompt
                    st.rerun()

    # Render Chat History
    for chat in st.session_state.chat_history:
        with st.chat_message(chat["role"]):
            st.markdown(chat["content"])
            if "trace" in chat and chat["trace"]:
                with st.expander("🔍 View Guardrail Trace"):
                    for step in chat["trace"]:
                        st.markdown(f"- **{step.get('node')}**: `{step.get('status')}`")

    # Render Pending Confirmation if any
    if st.session_state.pending_change_request:
        cr = st.session_state.pending_change_request
        st.warning("⚠️ **Confirmation Required:** Please review the proposed changes below before committing to database.")
        
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**Intent:** `{cr.get('intent')}`\n\n**Order:** `#{cr.get('order_id')}`\n\n**Proposed:** `{json.dumps(cr.get('proposed_change'))}`")
        with col2:
            st.markdown(f"**Current Value:** `{cr.get('preview', {}).get('current')}`")
            st.markdown(f"**New Value:** `{cr.get('preview', {}).get('new')}`")
            st.caption(f"Expires at: {cr.get('expires_at')}")

        btn_confirm, btn_cancel = st.columns([1, 1])
        with btn_confirm:
            if st.button("✅ Confirm & Apply", type="primary"):
                s_code, resp = api_request("POST", "/confirm", {
                    "request_id": cr["request_id"],
                    "action": "confirm",
                    "idempotency_key": cr["idempotency_key"]
                })
                if s_code == 200:
                    st.success(resp.get("message"))
                    st.session_state.chat_history.append({"role": "assistant", "content": f"✅ {resp.get('message')}"})
                else:
                    st.error(resp.get("detail", "Confirmation failed"))
                st.session_state.pending_change_request = None
                st.rerun()

        with btn_cancel:
            if st.button("❌ Decline Change"):
                s_code, resp = api_request("POST", "/confirm", {
                    "request_id": cr["request_id"],
                    "action": "cancel",
                    "idempotency_key": cr["idempotency_key"]
                })
                st.info(resp.get("message", "Change was cancelled."))
                st.session_state.chat_history.append({"role": "assistant", "content": f"❌ {resp.get('message')}"})
                st.session_state.pending_change_request = None
                st.rerun()

    # User Input
    user_input = st.chat_input("Enter your request") or st.session_state.queued_prompt
    st.session_state.queued_prompt = None
    st.caption("The agent can make mistakes. Changes always need your confirmation.")
    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            status_code, resp = api_request("POST", "/chat", {"message": user_input})
            if status_code == 200:
                reply = resp.get("reply", "")
                st.markdown(reply)
                
                # Check if confirmation is required
                if resp.get("needs_confirmation") and resp.get("change_request"):
                    st.session_state.pending_change_request = resp["change_request"]
                
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": reply,
                    "trace": resp.get("trace", [])
                })
                st.rerun()
            else:
                err_msg = resp.get("detail", "Error communicating with support agent.")
                st.error(err_msg)
                st.session_state.chat_history.append({"role": "assistant", "content": f"⚠️ {err_msg}"})


# ============================================================================
# PAGE 2: Orders
# ============================================================================
elif page == "📦 Orders":
    st.header("Your Orders")
    st.caption("Live customer orders fetched from the database")
    
    if st.button("🔄 Refresh Orders"):
        st.rerun()

    s_code, orders = api_request("GET", "/orders")
    if s_code == 200 and isinstance(orders, list):
        for o in orders:
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
                with col1:
                    st.subheader(f"Order #{o.get('order_ref')}")
                    st.caption(f"Order ID: {o.get('order_id')} | Version: {o.get('version')}")
                with col2:
                    status_val = o.get('status', '').upper()
                    if status_val == "PLACED":
                        st.info(f"Status: **{status_val}**")
                    elif status_val == "SHIPPED":
                        st.warning(f"Status: **{status_val}**")
                    elif status_val == "CANCELLED":
                        st.error(f"Status: **{status_val}**")
                    else:
                        st.success(f"Status: **{status_val}**")
                with col3:
                    st.markdown(f"**Total:** `${o.get('total_amount')}`")
                    st.caption(f"Delivery: {o.get('delivery_date')}")
                with col4:
                    st.markdown(f"**Shipping Address:**\n`{o.get('shipping_address')}`")

                # Show items
                items = o.get("items", [])
                if items:
                    with st.expander("📦 View Items in this Order"):
                        for it in items:
                            prod = it.get("product") or {}
                            st.write(f"- **{prod.get('name', 'Product')}** (Qty: {it.get('quantity')}) - `${it.get('item_price')}`")
    else:
        st.info("No orders found or backend is offline.")


# ============================================================================
# PAGE 3: Audit Log
# ============================================================================
else:
    st.header("Security & Compliance Audit Log")
    st.caption("Append-only audit trail with masked PII and rule evaluation")
    
    if st.button("🔄 Refresh Audit Log"):
        st.rerun()

    s_code, logs = api_request("GET", "/audit")
    if s_code == 200 and isinstance(logs, list):
        if not logs:
            st.info("No audit logs recorded yet. Try changing an address or cancelling an order.")
        else:
            for log in reversed(logs):
                dec = log.get("decision", "").upper()
                badge_type = "🟢" if dec == "APPROVED" else ("🔴" if dec == "BLOCKED" else "🟡")
                with st.container(border=True):
                    st.markdown(f"{badge_type} **Action:** `{log.get('action')}` | **Decision:** `{dec}` | **Order:** `#{log.get('order_id')}` | **Latency:** `{log.get('latency_ms')}ms`")
                    st.caption(f"Audit ID: {log.get('audit_id')} | Time: {log.get('created_at')}")
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write("**Before State (Masked):**", log.get("before_state"))
                    with c2:
                        st.write("**After State (Masked):**", log.get("after_state"))
    else:
        st.info("Audit logs unavailable or backend is offline.")
