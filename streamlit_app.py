"""
Streamlit Web Demo for Autonomous Customer Support Agent (Team Logic).
Dark, sleek, enterprise-grade AI interface matching the Resolvo design system.
Connects with FastAPI backend endpoints:
- GET /health
- POST /login
- GET /orders
- POST /chat
- POST /confirm
- GET /audit
"""
import json
from datetime import datetime
import requests
import streamlit as st

API_BASE_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="Logic · Autonomous AI Support",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
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

# High-fidelity Pro Dark Theme CSS injection
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }

    /* Overall Dark Canvas */
    .stApp {
        background-color: #0b0c10 !important;
        color: #e2e8f0;
    }

    /* Top header bar transparency */
    header[data-testid="stHeader"] {
        background: transparent !important;
    }

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #111318 !important;
        border-right: 1px solid #1e222d !important;
        width: 300px !important;
    }

    section[data-testid="stSidebar"] .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }

    /* Pro Brand Header in Sidebar */
    .brand-container {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 1.2rem;
    }
    .brand-icon {
        width: 36px;
        height: 36px;
        border-radius: 10px;
        background: linear-gradient(135deg, #1d4ed8, #3b82f6);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.2rem;
        color: #fff;
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
    }
    .brand-title-wrap {
        display: flex;
        flex-direction: column;
    }
    .brand-title {
        font-size: 1.15rem;
        font-weight: 700;
        color: #ffffff;
        letter-spacing: -0.02em;
        line-height: 1.2;
    }
    .brand-subtitle {
        font-size: 0.72rem;
        color: #818cf8;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .version-tag {
        font-size: 0.65rem;
        background: #1e2230;
        color: #94a3b8;
        border: 1px solid #2d3345;
        padding: 2px 7px;
        border-radius: 999px;
        margin-left: auto;
    }

    /* Section Subheaders in Sidebar */
    .side-section-label {
        font-size: 0.68rem;
        font-weight: 700;
        color: #64748b;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-top: 1.4rem;
        margin-bottom: 0.6rem;
    }

    /* History Timeline Item */
    .history-item {
        display: flex;
        align-items: flex-start;
        gap: 9px;
        font-size: 0.78rem;
        color: #94a3b8;
        padding: 6px 8px;
        border-radius: 8px;
        margin-bottom: 4px;
        line-height: 1.35;
        transition: background 0.15s ease;
    }
    .history-item:hover {
        background: #181c26;
        color: #f1f5f9;
        cursor: pointer;
    }
    .history-dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: #3b82f6;
        margin-top: 5px;
        flex-shrink: 0;
    }

    /* Center Welcome Hero */
    .hero-wrap {
        text-align: center;
        padding: 2.2rem 1rem 1.2rem;
        max-width: 820px;
        margin: 0 auto;
    }
    .hero-logo-box {
        width: 64px;
        height: 64px;
        margin: 0 auto 1.1rem;
        border-radius: 18px;
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.9rem;
        color: #ffffff;
        box-shadow: 0 8px 30px rgba(37, 99, 235, 0.35);
    }
    .hero-hello {
        color: #94a3b8;
        font-size: 0.92rem;
        font-weight: 500;
        margin-bottom: 0.3rem;
    }
    .hero-heading {
        font-size: 2.2rem;
        font-weight: 700;
        color: #f8fafc;
        letter-spacing: -0.03em;
        margin-bottom: 1.3rem;
    }

    /* Top Pill Badges */
    .pill-group {
        display: flex;
        justify-content: center;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 2rem;
    }
    .badge-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: #151821;
        border: 1px solid #232838;
        color: #cbd5e1;
        font-size: 0.78rem;
        padding: 5px 12px;
        border-radius: 999px;
        cursor: pointer;
        transition: all 0.2s;
    }
    .badge-pill:hover {
        background: #1e2433;
        border-color: #3b82f6;
        color: #fff;
    }

    /* 4 Pro Hero Action Cards */
    .pro-card {
        background: #13161f;
        border: 1px solid #1f2433;
        border-radius: 14px;
        padding: 1.2rem 1rem;
        text-align: left;
        height: 100%;
        transition: transform 0.15s, border-color 0.2s, box-shadow 0.2s;
        cursor: pointer;
    }
    .pro-card:hover {
        transform: translateY(-2px);
        border-color: #3b82f6;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
    }
    .card-icon-badge {
        width: 34px;
        height: 34px;
        border-radius: 9px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.1rem;
        margin-bottom: 0.8rem;
    }
    .badge-red { background: rgba(239, 68, 68, 0.15); color: #f87171; }
    .badge-green { background: rgba(16, 185, 129, 0.15); color: #34d399; }
    .badge-amber { background: rgba(245, 158, 11, 0.15); color: #fbbf24; }
    .badge-purple { background: rgba(139, 92, 246, 0.15); color: #c084fc; }

    .card-title {
        font-size: 0.88rem;
        font-weight: 600;
        color: #f1f5f9;
        margin-bottom: 0.35rem;
        line-height: 1.3;
    }
    .card-desc {
        font-size: 0.75rem;
        color: #828fa3;
        line-height: 1.4;
    }

    /* Streamlit Default Buttons Customization */
    div.stButton > button {
        background: #141722 !important;
        border: 1px solid #232838 !important;
        border-radius: 10px !important;
        color: #e2e8f0 !important;
        font-weight: 500 !important;
        font-size: 0.82rem !important;
        padding: 0.45rem 0.9rem !important;
        transition: all 0.2s ease !important;
    }
    div.stButton > button:hover {
        background: #1c2233 !important;
        border-color: #3b82f6 !important;
        color: #ffffff !important;
    }
    div.stButton > button[kind="primary"] {
        background: #2563eb !important;
        border-color: #2563eb !important;
        color: #ffffff !important;
        font-weight: 600 !important;
    }
    div.stButton > button[kind="primary"]:hover {
        background: #1d4ed8 !important;
        border-color: #1d4ed8 !important;
    }

    /* Right Tools Panel styling */
    .tool-panel {
        background: #111319;
        border: 1px solid #1e222e;
        border-radius: 14px;
        padding: 1.2rem;
    }
    .notice-card {
        background: #1c1810;
        border: 1px solid #3d2f13;
        border-radius: 10px;
        padding: 0.85rem;
        margin-bottom: 1rem;
    }
    .notice-title {
        color: #f59e0b;
        font-size: 0.82rem;
        font-weight: 600;
        margin-bottom: 0.25rem;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .notice-body {
        color: #d97706;
        font-size: 0.72rem;
        line-height: 1.4;
    }

    .tool-item-card {
        background: #141720;
        border: 1px solid #1f2432;
        border-radius: 10px;
        padding: 0.75rem 0.9rem;
        margin-bottom: 0.75rem;
    }
    .tool-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 0.3rem;
    }
    .tool-name {
        font-size: 0.82rem;
        font-weight: 600;
        color: #f1f5f9;
    }
    .tool-badge {
        font-size: 0.68rem;
        padding: 2px 7px;
        border-radius: 999px;
    }
    .badge-active { background: #064e3b; color: #34d399; }
    .badge-locked { background: #3730a3; color: #a5b4fc; }

    /* Modern Confirmation Card */
    .confirmation-container {
        background: #131722;
        border: 1px solid #2563eb;
        border-radius: 14px;
        padding: 1.3rem;
        margin: 1.2rem 0;
        box-shadow: 0 4px 20px rgba(37, 99, 235, 0.2);
    }

    /* Chat Messages */
    div[data-testid="stChatMessage"] {
        background: #12151e !important;
        border: 1px solid #1c2130 !important;
        border-radius: 14px !important;
        padding: 1rem !important;
        margin-bottom: 0.85rem !important;
    }

    /* Footer text */
    .app-disclaimer {
        text-align: center;
        font-size: 0.72rem;
        color: #64748b;
        margin-top: 1.5rem;
    }
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
        return 500, {"error": f"Backend offline ({API_BASE_URL}). Run: python -m uvicorn main:app", "detail": str(e)}


# ============================================================================
# SIDEBAR: Resolvo-inspired Navigation, History Timeline, Customer Card
# ============================================================================
with st.sidebar:
    st.markdown(
        """
        <div class="brand-container">
            <div class="brand-icon">🤖</div>
            <div class="brand-title-wrap">
                <span class="brand-title">Logic</span>
                <span class="brand-subtitle">AI-Powered Support</span>
            </div>
            <span class="version-tag">v1.0 Pro</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Search bar & Quick action
    search_q = st.text_input("Search", placeholder="🔍 Search orders, policies... (⌘S)", label_visibility="collapsed")
    if st.button("＋  New Conversation", use_container_width=True, type="primary"):
        st.session_state.chat_history = []
        st.session_state.pending_change_request = None
        st.session_state.queued_prompt = None
        st.rerun()

    # Views Navigation
    st.markdown('<p class="side-section-label">NAVIGATE</p>', unsafe_allow_html=True)
    page = st.radio(
        "Navigate",
        ["💬 Ask Logic", "📦 Orders Hub", "🛡️ Security & Audit"],
        label_visibility="collapsed",
    )

    # Activity Timeline (Resolvo replica)
    st.markdown('<p class="side-section-label">YESTERDAY</p>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="history-item"><div class="history-dot"></div><span>14 customer requests auto-resolved</span></div>
        <div class="history-item"><div class="history-dot"></div><span>Order #10023 address verified</span></div>
        <div class="history-item"><div class="history-dot"></div><span>2 changes escalated for confirmation</span></div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<p class="side-section-label">THIS WEEK</p>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="history-item"><div class="history-dot"></div><span>Zero PII leakage detected</span></div>
        <div class="history-item"><div class="history-dot"></div><span>Fulfillment cutoff guardrail active</span></div>
        <div class="history-item"><div class="history-dot"></div><span>Audit trail synced to logic.db</span></div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # Session Profile Card
    status_code, health = api_request("GET", "/health")
    backend_online = (status_code == 200)

    st.markdown(
        f"""
        <div style="background:#151822; border:1px solid #232838; border-radius:10px; padding:0.75rem; margin-bottom:0.7rem;">
            <div style="display:flex; align-items:center; gap:10px;">
                <div style="width:32px; height:32px; border-radius:50%; background:#2563eb; display:flex; align-items:center; justify-content:center; font-weight:700; color:#fff;">AS</div>
                <div>
                    <div style="font-size:0.82rem; font-weight:600; color:#f8fafc;">Alice Smith</div>
                    <div style="font-size:0.7rem; color:#94a3b8;">{st.session_state.customer_email}</div>
                </div>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-top:0.5rem; font-size:0.7rem;">
                <span style="color:#64748b;">Backend Status:</span>
                <span style="color:{'#34d399' if backend_online else '#f87171'}; font-weight:600;">
                    {'● FastAPI 8000 Online' if backend_online else '○ Offline'}
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("🗑️ Clear Conversation", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.pending_change_request = None
        st.session_state.queued_prompt = None
        st.rerun()


# ============================================================================
# PAGE 1: 💬 Ask Logic (Conversational Agent with Hero & Right Tools Panel)
# ============================================================================
if page == "💬 Ask Logic":
    # 2-column layout: Main Chat (70%) + Right Guardrail/Tools Inspector (30%)
    col_main, col_tools = st.columns([7, 3], gap="medium")

    with col_main:
        # Welcome Hero (shown when no prior chat)
        if not st.session_state.chat_history and not st.session_state.pending_change_request:
            st.markdown(
                """
                <div class="hero-wrap">
                    <div class="hero-logo-box">🤖</div>
                    <div class="hero-hello">Hello! Alice Smith</div>
                    <div class="hero-heading">How can I help you today?</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Top Pill Chips
            st.markdown(
                """
                <div class="pill-group">
                    <span class="badge-pill">📍 Order Address Guardrails ✕</span>
                    <span class="badge-pill">🚚 Live Package Tracking ✕</span>
                    <span class="badge-pill">🛡️ Strict PII Masking ✕</span>
                    <span class="badge-pill">⚡ Immutable Audit Ledger ✕</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # 4 Pro Action Cards in a 4-column row
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(
                    """
                    <div class="pro-card">
                        <div class="card-icon-badge badge-red">📍</div>
                        <div class="card-title">Modify Address</div>
                        <div class="card-desc">Safely change shipping address before courier dispatch cutoff.</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button("Change Address", key="act_addr", use_container_width=True):
                    st.session_state.queued_prompt = "Change shipping address for order 10023 to 12 MG Road, Pune"
                    st.rerun()

            with c2:
                st.markdown(
                    """
                    <div class="pro-card">
                        <div class="card-icon-badge badge-green">🚚</div>
                        <div class="card-title">Track Orders</div>
                        <div class="card-desc">Inspect real-time order status, fulfillment stage & estimated delivery.</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button("Track #10023", key="act_track", use_container_width=True):
                    st.session_state.queued_prompt = "Track order 10023"
                    st.rerun()

            with c3:
                st.markdown(
                    """
                    <div class="pro-card">
                        <div class="card-icon-badge badge-amber">❌</div>
                        <div class="card-title">Cancel Order</div>
                        <div class="card-desc">Request full cancellation for unshipped orders with audit preview.</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button("Cancel #10023", key="act_cancel", use_container_width=True):
                    st.session_state.queued_prompt = "Cancel order 10023"
                    st.rerun()

            with c4:
                st.markdown(
                    """
                    <div class="pro-card">
                        <div class="card-icon-badge badge-purple">🛡️</div>
                        <div class="card-title">Test Guardrail</div>
                        <div class="card-desc">Try modifying already-shipped order #10024 to trigger automated block.</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button("Test Guardrail", key="act_guard", use_container_width=True):
                    st.session_state.queued_prompt = "Change shipping address for order 10024 to 55 Lake Road"
                    st.rerun()

            st.write("")  # spacing

        # Render Chat History
        for chat in st.session_state.chat_history:
            avatar_icon = "👤" if chat["role"] == "user" else "🤖"
            with st.chat_message(chat["role"], avatar=avatar_icon):
                st.markdown(chat["content"])
                if chat.get("trace"):
                    with st.expander("🔍 Guardrail Decision & Latency Trace", expanded=False):
                        for step in chat["trace"]:
                            node_name = step.get('node', 'Rule')
                            node_stat = step.get('status', 'OK')
                            color = "#34d399" if node_stat in ["passed", "success", "OK"] else "#f59e0b"
                            st.markdown(f"- **{node_name}**: <span style='color:{color}; font-weight:600;'>{node_stat}</span>", unsafe_allow_html=True)

        # Render Pending Confirmation (Guardrail verification before DB write)
        if st.session_state.pending_change_request:
            cr = st.session_state.pending_change_request
            st.markdown(
                f"""
                <div class="confirmation-container">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.75rem;">
                        <span style="font-size:0.95rem; font-weight:700; color:#f8fafc;">
                            ⚠️ Confirmation Required: State Modification
                        </span>
                        <span style="font-size:0.75rem; background:#1e3a8a; color:#bfdbfe; padding:2px 8px; border-radius:999px;">
                            Expires in 5 min
                        </span>
                    </div>
                    <div style="font-size:0.8rem; color:#94a3b8; margin-bottom:0.8rem;">
                        The agent has prepared a database update for <b>Order #{cr.get('order_id')}</b>. Please verify the preview below before applying:
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            diff_col1, diff_col2 = st.columns(2)
            with diff_col1:
                st.markdown(f"**Current State (Database):**\n```json\n{json.dumps(cr.get('preview', {}).get('current'), indent=2)}\n```")
            with diff_col2:
                st.markdown(f"**Proposed State (To Commit):**\n```json\n{json.dumps(cr.get('preview', {}).get('new'), indent=2)}\n```")

            b_conf, b_abort = st.columns([1, 1])
            with b_conf:
                if st.button("✅ Confirm & Apply Changes", type="primary", use_container_width=True):
                    s_code, resp = api_request("POST", "/confirm", {
                        "request_id": cr["request_id"],
                        "action": "confirm",
                        "idempotency_key": cr["idempotency_key"]
                    })
                    if s_code == 200:
                        msg = resp.get("message", "Order successfully updated.")
                        st.session_state.chat_history.append({"role": "assistant", "content": f"✅ **Applied:** {msg}"})
                    else:
                        st.session_state.chat_history.append({"role": "assistant", "content": f"❌ **Error:** {resp.get('detail')}"})
                    st.session_state.pending_change_request = None
                    st.rerun()

            with b_abort:
                if st.button("✕ Decline & Discard", use_container_width=True):
                    s_code, resp = api_request("POST", "/confirm", {
                        "request_id": cr["request_id"],
                        "action": "cancel",
                        "idempotency_key": cr["idempotency_key"]
                    })
                    st.session_state.chat_history.append({"role": "assistant", "content": "❌ Change request cancelled."})
                    st.session_state.pending_change_request = None
                    st.rerun()

        # Chat Input Bar
        user_input = st.chat_input("Enter your request (e.g. 'Change shipping address for order 10023 to 12 MG Road, Pune')") or st.session_state.queued_prompt
        st.session_state.queued_prompt = None

        if user_input:
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            with st.chat_message("user", avatar="👤"):
                st.markdown(user_input)

            with st.chat_message("assistant", avatar="🤖"):
                with st.spinner("Logic is evaluating request & safety guardrails..."):
                    status_code, resp = api_request("POST", "/chat", {"message": user_input})

                if status_code == 200:
                    reply = resp.get("reply", "")
                    st.markdown(reply)

                    if resp.get("needs_confirmation") and resp.get("change_request"):
                        st.session_state.pending_change_request = resp["change_request"]

                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": reply,
                        "trace": resp.get("trace", [])
                    })
                    st.rerun()
                else:
                    err_msg = resp.get("detail", "Failed to communicate with Logic agent backend.")
                    st.error(err_msg)
                    st.session_state.chat_history.append({"role": "assistant", "content": f"⚠️ {err_msg}"})

        st.markdown(
            '<div class="app-disclaimer">Logic AI can make mistakes. All database modifications require customer confirmation. · Your privacy & Logic</div>',
            unsafe_allow_html=True,
        )

    # ========================================================================
    # RIGHT PANEL: Tools, Guardrail Stability & Live Snapshot (Resolvo replica)
    # ========================================================================
    with col_tools:
        st.markdown(
            """
            <div class="tool-panel">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
                    <div style="font-size:0.95rem; font-weight:700; color:#f8fafc;">Active Tools</div>
                    <div style="font-size:0.75rem; background:#1e2433; color:#94a3b8; padding:3px 8px; border-radius:6px;">Docs</div>
                </div>
                <div class="notice-card">
                    <div class="notice-title">⚠️ Tool Stability & Safety Notice</div>
                    <div class="notice-body">
                        Tools in this panel directly mutate operational tables. Every invocation is governed by strict deterministic guardrails.
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="tool-item-card">
                <div class="tool-header">
                    <span class="tool-name">📍 Address Mutation Tool</span>
                    <span class="tool-badge badge-active">Active</span>
                </div>
                <div style="font-size:0.72rem; color:#828fa3;">
                    Allowed only when status = <code>placed</code>. Enforces 24h cutoff & min length 5.
                </div>
            </div>
            <div class="tool-item-card">
                <div class="tool-header">
                    <span class="tool-name">❌ Cancellation Engine</span>
                    <span class="tool-badge badge-active">Active</span>
                </div>
                <div style="font-size:0.72rem; color:#828fa3;">
                    Triggers instant refund and order state transition to <code>cancelled</code>.
                </div>
            </div>
            <div class="tool-item-card">
                <div class="tool-header">
                    <span class="tool-name">🔒 Version Concurrency Lock</span>
                    <span class="tool-badge badge-locked">Enforced</span>
                </div>
                <div style="font-size:0.72rem; color:#828fa3;">
                    Optimistic locking detects mid-flight order updates to prevent stale writes.
                </div>
            </div>
            <div class="tool-item-card">
                <div class="tool-header">
                    <span class="tool-name">🛡️ PII Masking Engine</span>
                    <span class="tool-badge badge-active">Active</span>
                </div>
                <div style="font-size:0.72rem; color:#828fa3;">
                    Redacts street addresses in audit trails to ensure compliance.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("---")
        st.markdown("<div style='font-size:0.85rem; font-weight:600; color:#f8fafc; margin-bottom:0.5rem;'>⚡ Quick Order Snapshot</div>", unsafe_allow_html=True)
        s_code, orders_preview = api_request("GET", "/orders")
        if s_code == 200 and isinstance(orders_preview, list):
            for op in orders_preview:
                st_color = "#38bdf8" if op.get("status") == "placed" else ("#fbbf24" if op.get("status") == "shipped" else "#94a3b8")
                st.markdown(
                    f"""
                    <div style="background:#13151f; border:1px solid #1f2331; border-radius:8px; padding:0.6rem; margin-bottom:0.5rem; font-size:0.75rem;">
                        <div style="display:flex; justify-content:space-between; font-weight:600;">
                            <span style="color:#f1f5f9;">#{op.get('order_ref')}</span>
                            <span style="color:{st_color}; text-transform:uppercase;">{op.get('status')}</span>
                        </div>
                        <div style="color:#64748b; margin-top:2px;">{op.get('shipping_address')}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


# ============================================================================
# PAGE 2: 📦 Orders Hub
# ============================================================================
elif page == "📦 Orders Hub":
    st.markdown(
        """
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.2rem;">
            <div>
                <h2 style="font-size:1.6rem; font-weight:700; color:#f8fafc; margin:0;">Customer Orders Hub</h2>
                <p style="font-size:0.82rem; color:#828fa3; margin:0;">Live records directly fetched from relational database</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("🔄 Refresh Orders Data"):
        st.rerun()

    s_code, orders = api_request("GET", "/orders")
    if s_code == 200 and isinstance(orders, list):
        for o in orders:
            status_val = o.get('status', '').upper()
            badge_class = "badge-green" if status_val == "DELIVERED" else ("badge-amber" if status_val == "SHIPPED" else ("badge-red" if status_val == "CANCELLED" else "badge-purple"))

            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
                with c1:
                    st.markdown(f"<div style='font-size:1.1rem; font-weight:700; color:#fff;'>Order #{o.get('order_ref')}</div>", unsafe_allow_html=True)
                    st.caption(f"Booking ID: `{o.get('booking_id')}` | DB Version: {o.get('version')}")
                with c2:
                    st.markdown(f"**Status:** <span class='card-icon-badge {badge_class}' style='display:inline; padding:3px 8px; border-radius:6px; font-size:0.75rem; font-weight:600;'>{status_val}</span>", unsafe_allow_html=True)
                    st.caption(f"Payment: {o.get('payment_method')} ({o.get('payment_status')})")
                with c3:
                    st.markdown(f"**Total:** `${o.get('total_amount')}`")
                    st.caption(f"Delivery: {o.get('delivery_date')}")
                with c4:
                    st.markdown(f"**Shipping Address:**\n`{o.get('shipping_address')}`")

                items = o.get("items", [])
                if items:
                    with st.expander("📦 Ordered Line Items"):
                        for it in items:
                            prod = it.get("product") or {}
                            st.markdown(f"- **{prod.get('name', 'Item')}** — Qty: `{it.get('quantity')}` × `${it.get('item_price')}` (Category: `{prod.get('category')}`)")
    else:
        st.info("No orders found or backend service is offline.")


# ============================================================================
# PAGE 3: 🛡️ Security & Audit Log
# ============================================================================
else:
    st.markdown(
        """
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.2rem;">
            <div>
                <h2 style="font-size:1.6rem; font-weight:700; color:#f8fafc; margin:0;">Security & Compliance Audit Trail</h2>
                <p style="font-size:0.82rem; color:#828fa3; margin:0;">Tamper-evident, masked PII audit ledger evaluating business rules</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("🔄 Refresh Audit Logs"):
        st.rerun()

    s_code, logs = api_request("GET", "/audit")
    if s_code == 200 and isinstance(logs, list):
        if not logs:
            st.info("No audit logs recorded yet. Try modifying an address or cancelling an order in the 'Ask Logic' chat.")
        else:
            for log in reversed(logs):
                dec = log.get("decision", "").upper()
                badge_color = "#34d399" if dec == "APPROVED" else ("#f87171" if dec == "BLOCKED" else "#fbbf24")
                with st.container(border=True):
                    col_h1, col_h2 = st.columns([3, 1])
                    with col_h1:
                        st.markdown(
                            f"<span style='color:{badge_color}; font-weight:700;'>● {dec}</span> · <b>Action:</b> <code>{log.get('action')}</code> · <b>Order ID:</b> <code>#{log.get('order_id')}</code>",
                            unsafe_allow_html=True,
                        )
                        st.caption(f"Audit UUID: {log.get('request_id')} | Created: {log.get('created_at')}")
                    with col_h2:
                        st.metric("Latency", f"{log.get('latency_ms', 12)} ms")

                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("**Before State (Masked PII):**")
                        st.json(log.get("before_state") or {})
                    with c2:
                        st.markdown("**After State (Committed):**")
                        st.json(log.get("after_state") or {})
    else:
        st.info("Audit logs are currently unavailable or backend is offline.")
