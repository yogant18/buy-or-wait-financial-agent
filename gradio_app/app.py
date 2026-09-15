"""
app.py — Gradio Chatbot UI for Buy or Wait? Financial Agent
Hugging Face Spaces (Gradio SDK — FREE tier) deployment entry point.

Usage (local):
    python gradio_app/app.py
HF Spaces entry point must be: app.py at the repo root, or set in Space settings.
"""
import os
import re
import sys
import logging

# ── Path setup ────────────────────────────────────────────────────────────────
APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(APP_DIR)
CODE_DIR = os.path.join(REPO_ROOT, "code")
DATASET_DIR = os.path.join(REPO_ROOT, "dataset")
sys.path.insert(0, CODE_DIR)

# ── Load .env (local dev only) ────────────────────────────────────────────────
_env_path = os.path.join(REPO_ROOT, ".env")
if os.path.exists(_env_path):
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

import spaces
import gradio as gr

from data_loader import load_all_data
from ocr_extractor import extract_image_amounts
from message_parser import parse_all_messages
from financial_engine import detect_recurring_events, build_forecast, evaluate_plans
from llm_client import generate_decision_explanation_llm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gradio_app")

# ── Status icons ──────────────────────────────────────────────────────────────
STATUS_BADGE = {
    "affordable_now":       "🟢 **Affordable Now**",
    "affordable_with_plan": "🟡 **Affordable With a Plan**",
    "affordable_later":     "🟠 **Affordable Later**",
    "not_affordable":       "🔴 **Not Affordable**",
}
METHOD_LABEL = {
    "full_payment":     "Full Payment",
    "partial_payment":  "Partial Payment",
    "installments":     "Installment Plan",
    "wait":             "Wait",
    "not_recommended":  "Not Recommended",
}

# ── Dataset cache (loaded once) ───────────────────────────────────────────────
_CACHE: dict = {}


def _load_data():
    if not _CACHE:
        logger.info("Loading dataset from %s", DATASET_DIR)
        _CACHE["data"] = load_all_data(DATASET_DIR)
        _CACHE["image_amounts"] = extract_image_amounts(
            _CACHE["data"]["images"], _CACHE["data"]["events"], DATASET_DIR
        )
        _CACHE["amendments"] = parse_all_messages(_CACHE["data"]["messages"])
        logger.info(
            "Dataset ready — %d requests", len(_CACHE["data"]["requests"])
        )
    return _CACHE


# ── Parsers ───────────────────────────────────────────────────────────────────

def _parse_request_id(text: str):
    m = re.search(r"\brequest[_\s-]?(\d+)\b", text, re.IGNORECASE)
    return f"request_{m.group(1)}" if m else None


def _parse_user_id(text: str):
    m = re.search(r"\buser[_\s-]?(\d+)\b", text, re.IGNORECASE)
    return f"user_{m.group(1).zfill(2)}" if m else None


# ── Formatter ─────────────────────────────────────────────────────────────────

def _format_result(row, result: dict, explanation: str) -> str:
    cache = _load_data()
    uid = str(row.get("user_id", ""))
    prof_df = cache["data"]["profiles"]
    currency = "?"
    prows = prof_df[prof_df["user_id"] == uid]
    if not prows.empty:
        currency = str(prows.iloc[0]["home_currency"])

    status  = result["affordability_status"]
    method  = result["recommended_payment_method"]
    safe    = result["amount_safe_to_pay"]
    total   = float(row.get("requested_amount", 0))
    earliest = result.get("earliest_date_for_full_payment", "")
    plan     = result.get("payment_plan", "none")
    spending = result.get("spending_changes_needed", "none")

    # Payment plan lines
    plan_md = ""
    if plan and plan != "none":
        lines = []
        for entry in plan.split("|"):
            parts = entry.split(":")
            if len(parts) == 2:
                lines.append(f"  - `{parts[0]}` → **{currency} {float(parts[1]):,.2f}**")
        plan_md = "\n".join(lines)
    else:
        plan_md = "  _No multi-step plan required_"

    earliest_line = f"\n**Earliest Full Payment Date:** {earliest}" if earliest else ""
    spending_line = f"\n**Spending Changes:** `{spending}`" if spending and spending != "none" else ""

    return f"""## 💰 Buy or Wait? — Decision Report

| Field | Value |
|---|---|
| **Request ID** | `{row.get('request_id', '?')}` |
| **User** | `{row.get('user_id', '?')}` |
| **Type** | {row.get('request_type', '?')} |
| **Amount Requested** | {currency} {total:,.2f} |
| **Request Date** | {row.get('request_date', '?')} |
| **Deadline** | {row.get('desired_completion_date', '?')} |

---

### {STATUS_BADGE.get(status, status)}
**Recommended Method:** {METHOD_LABEL.get(method, method)}
**Safe to Pay Today:** {currency} {safe:,.2f}{earliest_line}{spending_line}

### 💳 Payment Plan
{plan_md}

---

### 🧠 Advisor Explanation
> {explanation}

---
_Try: `check request_50` · `user_03 can I pay?` · `list` · `help`_"""


def _list_requests(n: int = 15) -> str:
    cache = _load_data()
    df = cache["data"]["requests"]
    rows = df.head(n)
    lines = [f"**{len(df)} requests available.** Here are {n}:\n"]
    for _, r in rows.iterrows():
        lines.append(
            f"- **{r['request_id']}** ({r['user_id']}) — "
            f"{r['request_type']} | {r['requested_amount']} on {r['request_date']}"
        )
    if len(df) > n:
        lines.append(f"\n_...type `list all` to see all {len(df)}_")
    return "\n".join(lines)


# ── Core chat function ────────────────────────────────────────────────────────

def _run_chat(message: str, history: list) -> str:
    """CPU-only financial analysis — all heavy work happens here."""
    text  = message.strip()
    lower = text.lower()

    # Help
    if lower in ("help", "?", "commands"):
        return """### 💡 How to Query

**By Request ID:**
```
check request_26
request_100
analyse request_42
```
**By User ID:**
```
user_05 can I buy a laptop?
I am user_12, should I make this payment?
```
**Browse:**
```
list
list all
```"""

    # List
    if lower.startswith("list"):
        n = 250 if "all" in lower else 15
        return _list_requests(n)

    # Parse
    request_id = _parse_request_id(text)
    user_id    = _parse_user_id(text)

    cache = _load_data()
    data  = cache["data"]
    df    = data["requests"]

    request_row = None
    note = ""

    if request_id:
        m = df[df["request_id"] == request_id]
        if not m.empty:
            request_row = m.iloc[0]

    elif user_id:
        user_reqs = df[df["user_id"] == user_id]
        if not user_reqs.empty:
            request_row = user_reqs.iloc[0]
            note = f"_Found {len(user_reqs)} request(s) for `{user_id}`. Analysing: **{request_row['request_id']}**_\n\n"

    if request_row is None:
        return (
            "⚠️ Couldn't find a matching request. Try:\n"
            "- `check request_26`\n"
            "- `user_05 can I pay?`\n"
            "- `list` to browse all requests"
        )

    # Run pipeline
    try:
        uid = str(request_row["user_id"])
        user_events    = data["events"][data["events"]["user_id"] == uid].copy()
        user_amendments = [a for a in cache["amendments"] if a["user_id"] == uid]
        options = data["payment_options"][
            data["payment_options"]["request_id"] == str(request_row["request_id"])
        ]

        for eid, amt in cache["image_amounts"].items():
            mask = user_events["event_id"] == eid
            if mask.any():
                user_events.loc[mask, "amount"] = amt

        request_date = request_row["request_date"]
        recurring    = detect_recurring_events(user_events, request_date)

        internal_eids = {
            a.get("related_event_id", "")
            for a in user_amendments
            if a["type"] == "INTERNAL_TRANSFER"
        }

        prows = data["profiles"][data["profiles"]["user_id"] == uid]
        if prows.empty:
            return "❌ No financial profile found for this user."

        profile       = prows.iloc[0]
        home_currency = str(profile["home_currency"])
        balance       = float(profile["current_available_balance"])
        min_bal       = float(profile["minimum_balance_to_keep"])

        daily_balances, all_projected = build_forecast(
            balance, user_events, recurring,
            request_date, home_currency, data["exchange_rates"],
            user_amendments, internal_eids,
        )

        result = evaluate_plans(
            request_row, profile, options, daily_balances,
            min_bal, all_projected, data["exchange_rates"], home_currency,
        )

        explanation = generate_decision_explanation_llm(
            result, profile, request_row, recurring_count=len(recurring)
        )

        return note + _format_result(request_row, result, explanation)

    except Exception as exc:
        logger.exception("Error processing request")
        return f"❌ **Error:** `{exc}`\n\nTry a different request ID."


# ── Gradio UI ─────────────────────────────────────────────────────────────────

WELCOME = """## 💰 Buy or Wait? — AI Financial Agent

I analyse your financial situation and tell you whether to **buy now**, **wait**, **use installments**, or **avoid** a purchase — based on your real financial profile, 90-day cash flow, and exchange rates.

---

**Quick start:**
- `check request_26` — analyse a specific request
- `user_27 can I buy a laptop?` — query by user ID
- `list` — browse available requests
- `help` — show all commands
"""

_theme = gr.themes.Soft(
    primary_hue="purple",
    secondary_hue="indigo",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "sans-serif"],
)


# Thin GPU wrapper — satisfies ZeroGPU requirement; real work is CPU-only in _run_chat
@spaces.GPU(duration=120)
def chat(message: str, history: list) -> str:
    return _run_chat(message, history)


demo = gr.ChatInterface(
    fn=chat,
    description=WELCOME,
    examples=[
        "check request_26",
        "check request_50",
        "user_27 can I buy a laptop?",
        "list",
        "help",
    ],
)


if __name__ == "__main__":
    _load_data()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
        theme=_theme,
    )
