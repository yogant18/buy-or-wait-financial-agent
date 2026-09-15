"""
app.py — Chainlit UI for Buy or Wait? Financial Agent
Hugging Face Spaces deployment entry point.

Usage:
    chainlit run chainlit_app/app.py --host 0.0.0.0 --port 7860
"""
import os
import re
import sys
import logging

import chainlit as cl

# ── Path setup: resolve repo root so code/ and dataset/ are importable ──
APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(APP_DIR)
CODE_DIR = os.path.join(REPO_ROOT, "code")
DATASET_DIR = os.path.join(REPO_ROOT, "dataset")

sys.path.insert(0, CODE_DIR)

# ── Load .env if present (local dev) ──
_env_path = os.path.join(REPO_ROOT, ".env")
if os.path.exists(_env_path):
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

from data_loader import load_all_data
from ocr_extractor import extract_image_amounts
from message_parser import parse_all_messages
from financial_engine import detect_recurring_events, build_forecast, evaluate_plans
from llm_client import generate_decision_explanation_llm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chainlit_app")

# ── Status emoji map ──
STATUS_EMOJI = {
    "affordable_now": "✅",
    "affordable_with_plan": "📅",
    "affordable_later": "⏳",
    "not_affordable": "❌",
}
METHOD_LABEL = {
    "full_payment": "Full Payment",
    "partial_payment": "Partial Payment",
    "installments": "Installment Plan",
    "wait": "Wait",
    "not_recommended": "Not Recommended",
}

# ── Global dataset cache (loaded once at startup) ──
_DATA_CACHE = {}


def _load_data_once():
    """Load dataset into memory once and cache."""
    if not _DATA_CACHE:
        logger.info("Loading dataset from %s ...", DATASET_DIR)
        _DATA_CACHE["data"] = load_all_data(DATASET_DIR)
        _DATA_CACHE["image_amounts"] = extract_image_amounts(
            _DATA_CACHE["data"]["images"],
            _DATA_CACHE["data"]["events"],
            DATASET_DIR,
        )
        _DATA_CACHE["amendments"] = parse_all_messages(
            _DATA_CACHE["data"]["messages"]
        )
        logger.info("Dataset loaded. %d requests available.", len(_DATA_CACHE["data"]["requests"]))
    return _DATA_CACHE


def _parse_request_id(text: str):
    """Extract request_id like 'request_42' from user text."""
    match = re.search(r"\brequest[_\s-]?(\d+)\b", text, re.IGNORECASE)
    if match:
        return f"request_{match.group(1)}"
    return None


def _parse_user_id(text: str):
    """Extract user_id like 'user_05' from user text."""
    match = re.search(r"\buser[_\s-]?(\d+)\b", text, re.IGNORECASE)
    if match:
        num = match.group(1).zfill(2)
        return f"user_{num}"
    return None


def _format_decision(row, result, explanation) -> str:
    """Format the financial decision as a rich Markdown message."""
    status = result["affordability_status"]
    method = result["recommended_payment_method"]
    emoji = STATUS_EMOJI.get(status, "💬")
    method_label = METHOD_LABEL.get(method, method)

    amount_safe = result["amount_safe_to_pay"]
    requested = float(row.get("requested_amount", 0))
    currency = "?"

    cache = _load_data_once()
    uid = str(row.get("user_id", ""))
    profile_df = cache["data"]["profiles"]
    profile_rows = profile_df[profile_df["user_id"] == uid]
    if not profile_rows.empty:
        currency = str(profile_rows.iloc[0]["home_currency"])

    payment_plan = result.get("payment_plan", "none")
    earliest = result.get("earliest_date_for_full_payment", "")
    spending = result.get("spending_changes_needed", "none")

    # Build plan block
    plan_lines = []
    if payment_plan and payment_plan != "none":
        for entry in payment_plan.split("|"):
            parts = entry.split(":")
            if len(parts) == 2:
                plan_lines.append(f"  - `{parts[0]}` - **{currency} {float(parts[1]):,.2f}**")

    plan_block = "\n".join(plan_lines) if plan_lines else "  _No multi-step plan required_"

    badges = {
        "affordable_now": "🟢 Affordable Now",
        "affordable_with_plan": "🟡 Affordable With a Plan",
        "affordable_later": "🟠 Affordable Later",
        "not_affordable": "🔴 Not Affordable",
    }

    msg = f"""
## {emoji} Buy or Wait? — Decision Report

| Field | Value |
|---|---|
| **Request ID** | `{row.get('request_id', '?')}` |
| **User** | `{row.get('user_id', '?')}` |
| **Requested Amount** | {currency} {requested:,.2f} |
| **Request Date** | {row.get('request_date', '?')} |
| **Deadline** | {row.get('desired_completion_date', '?')} |

---

### {badges.get(status, status)}
**Recommended Method:** {method_label}
**Safe to Pay Today:** {currency} {amount_safe:,.2f}
{"**Earliest Full Payment Date:** " + str(earliest) if earliest else ""}
{"**Spending Changes Needed:** `" + spending + "`" if spending and spending != "none" else ""}

### Payment Plan
{plan_block}

---

### Advisor Explanation
> {explanation}

---
_Ask me about another request — e.g. `check request_50` or `user_03 can I pay rent?`_
"""
    return msg.strip()


def _list_available_requests(n: int = 10) -> str:
    cache = _load_data_once()
    requests_df = cache["data"]["requests"]
    sample = requests_df.head(n)
    lines = ["Here are some available request IDs you can query:\n"]
    for _, r in sample.iterrows():
        lines.append(
            f"- **{r['request_id']}** ({r['user_id']}) — {r['request_type']} "
            f"| {r.get('requested_amount', '?')} on {r.get('request_date', '?')}"
        )
    lines.append(f"\n_...and {len(requests_df) - n} more. Type `list all` to see everything._")
    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════
# Chainlit Handlers
# ════════════════════════════════════════════════════════════════

@cl.on_chat_start
async def on_chat_start():
    """Welcome message and dataset pre-load."""
    _load_data_once()

    welcome = """# Buy or Wait? — AI Financial Agent

Welcome! I analyse your financial situation and tell you whether to **buy now**, **wait**, **pay in installments**, or **avoid** a purchase.

### How to use me:
- Type a **request ID**: `check request_42`
- Type a **user ID** with context: `user_05 should I pay rent?`
- Type `list` to see available requests
- Type `help` for more examples

---
All decisions are grounded in your financial profile, 90-day cash flow forecast, and exchange rates.
"""
    await cl.Message(content=welcome).send()


@cl.on_message
async def on_message(message: cl.Message):
    """Handle incoming user messages."""
    text = message.content.strip()
    lower = text.lower()

    # ── Help ──
    if lower in ("help", "?", "commands"):
        help_msg = """### How to Query

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

**Browse requests:**
```
list
list all
```

**Examples from the dataset:**
```
check request_26
check request_50
check request_100
```
"""
        await cl.Message(content=help_msg).send()
        return

    # ── List requests ──
    if lower.startswith("list"):
        n = 250 if "all" in lower else 15
        await cl.Message(content=_list_available_requests(n)).send()
        return

    # ── Parse IDs ──
    request_id = _parse_request_id(text)
    user_id = _parse_user_id(text)

    cache = _load_data_once()
    data = cache["data"]
    requests_df = data["requests"]

    # ── Resolve request row ──
    request_row = None

    if request_id:
        matches = requests_df[requests_df["request_id"] == request_id]
        if not matches.empty:
            request_row = matches.iloc[0]

    elif user_id:
        user_requests = requests_df[requests_df["user_id"] == user_id]
        if not user_requests.empty:
            request_row = user_requests.iloc[0]
            await cl.Message(
                content=f"_Found {len(user_requests)} request(s) for `{user_id}`. Analysing the most recent: **{request_row['request_id']}**._"
            ).send()

    if request_row is None:
        await cl.Message(
            content=(
                "I couldn't find a matching request. Try:\n"
                "- `check request_26` (use a valid request ID)\n"
                "- `user_05 can I pay?` (use a valid user ID)\n"
                "- Type `list` to see all available requests\n\n"
                f"Your input: `{text}`"
            )
        ).send()
        return

    # ── Run analysis ──
    thinking_msg = await cl.Message(content="Analysing your financial position...").send()

    try:
        uid = str(request_row["user_id"])
        user_events = data["events"][data["events"]["user_id"] == uid].copy()
        user_amendments = [a for a in cache["amendments"] if a["user_id"] == uid]
        options = data["payment_options"][
            data["payment_options"]["request_id"] == str(request_row["request_id"])
        ]

        # Patch image amounts
        for eid, amt in cache["image_amounts"].items():
            mask = user_events["event_id"] == eid
            if mask.any():
                user_events.loc[mask, "amount"] = amt

        request_date = request_row["request_date"]
        recurring = detect_recurring_events(user_events, request_date)

        internal_transfer_eids = set()
        for a in user_amendments:
            if a["type"] == "INTERNAL_TRANSFER":
                internal_transfer_eids.add(a.get("related_event_id", ""))

        profile_rows = data["profiles"][data["profiles"]["user_id"] == uid]
        if profile_rows.empty:
            await thinking_msg.update(content="No financial profile found for this user.")
            return

        profile = profile_rows.iloc[0]
        home_currency = str(profile["home_currency"])
        current_balance = float(profile["current_available_balance"])
        min_balance = float(profile["minimum_balance_to_keep"])

        daily_balances, all_projected = build_forecast(
            current_balance, user_events, recurring,
            request_date, home_currency, data["exchange_rates"],
            user_amendments, internal_transfer_eids,
        )

        result = evaluate_plans(
            request_row, profile, options, daily_balances,
            min_balance, all_projected, data["exchange_rates"], home_currency,
        )

        explanation = generate_decision_explanation_llm(
            result, profile, request_row, recurring_count=len(recurring)
        )

        formatted = _format_decision(request_row, result, explanation)
        await thinking_msg.update(content=formatted)

    except Exception as exc:
        logger.exception("Error processing %s", request_row.get("request_id", "?"))
        await thinking_msg.update(
            content=f"Error processing request: `{exc}`\n\nPlease try another request ID."
        )
