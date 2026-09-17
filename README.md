# 💰 Buy or Wait? — AI-Powered Financial Decision Agent

> **HackerRank Orchestrate (September 2026) Hackathon Submission**

An intelligent financial agent that analyses your real financial profile and tells you whether to **buy now**, **wait**, **use installments**, or **avoid** a purchase — grounded in 90-day cash flow forecasting, fixed exchange rates, and LLM-powered explanations.

🚀 **[Live Demo on Render](https://buy-or-wait-financial-agent.onrender.com/)** &nbsp;[![Deploy Status](https://img.shields.io/badge/Render-Live-brightgreen?logo=render)](https://buy-or-wait-financial-agent.onrender.com/)

---

## ✨ Features

- **90-Day Cash Flow Forecasting** — Detects recurring payments, pending credits/debits, and essential expenses
- **Multi-Currency Support** — Fixed-date exchange rates for accurate cross-currency decisions
- **Smart Installment Analysis** — Evaluates all available payment options against user preferences
- **OCR Image Extraction** — Reads monetary amounts from images using EasyOCR with LLM fallback
- **Message Intelligence** — Parses messages to detect cancellations, amendments, and confirmations
- **LLM Explanations** — Groq-powered plain-English rationale with deterministic fallback
- **Zero Hallucination** — All financial decisions are computed deterministically in Python; LLM only writes the explanation

---

## 🤖 System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   User Request (CSV)                     │
└─────────────────┬───────────────────────────────────────┘
                  │
         ┌────────▼────────┐
         │   Data Loader   │  financial_profiles.csv
         │                 │  financial_events.csv
         │                 │  exchange_rates.csv
         │                 │  request_payment_options.csv
         └────────┬────────┘
                  │
    ┌─────────────▼─────────────┐
    │    Message & Image Parser  │  messages.csv + images/
    │  (EasyOCR + Groq LLM)     │
    └─────────────┬─────────────┘
                  │
    ┌─────────────▼─────────────┐
    │    Financial Engine        │  Recurring detection
    │    (100% Deterministic)    │  90-day balance forecast
    │                            │  Payment plan evaluator
    └─────────────┬─────────────┘
                  │
    ┌─────────────▼─────────────┐
    │    LLM Advisor (Groq)      │  Plain-English explanation
    │    + Deterministic Fallback│  with template fallback
    └─────────────┬─────────────┘
                  │
         ┌────────▼────────┐
         │   output.csv    │  250 rows with all 8 fields
         └─────────────────┘
```

---

## 📊 Output Schema

```csv
request_id, amount_safe_to_pay, affordability_status, recommended_payment_method,
payment_plan, earliest_date_for_full_payment, spending_changes_needed, decision_explanation
```

| Field | Values |
|---|---|
| `affordability_status` | `affordable_now` · `affordable_with_plan` · `affordable_later` · `not_affordable` |
| `recommended_payment_method` | `full_payment` · `partial_payment` · `installments` · `wait` · `not_recommended` |
| `payment_plan` | `YYYY-MM-DD:amount\|YYYY-MM-DD:amount` or `none` |

---

## 🛠️ Setup & Run

### Prerequisites
```bash
pip install pandas easyocr Pillow
```

### Environment
Create a `.env` file in the repo root:
```env
GROQ_API_KEY=gsk_your_key_here
```
Get a free key at [console.groq.com](https://console.groq.com). The agent works without it (uses deterministic fallback explanations).

### Run the CLI Agent
```bash
cd code
python main.py
```
Reads from `dataset/`, writes `dataset/output.csv`.

### Run the Gradio Chat UI (locally)
```bash
pip install gradio spaces
python app.py
# Open http://localhost:7860
```

---

## 🌐 Live Demo

The app is deployed on **Hugging Face Spaces** with a Gradio chat interface:

👉 **[huggingface.co/spaces/Sugarz3ro/buy-or-wait](https://huggingface.co/spaces/Sugarz3ro/buy-or-wait)**

### Chat commands:
| Command | What it does |
|---|---|
| `check request_26` | Full financial analysis for a request |
| `user_27 can I buy a laptop?` | Query by user ID |
| `list` | Browse all available requests |
| `help` | Show all commands |

---

## 📁 Project Structure

```
├── app.py                        # Gradio app entry point (HF Spaces)
├── requirements.txt              # Python dependencies
├── gradio_app/
│   └── app.py                    # Full Gradio chat UI implementation
├── code/
│   ├── main.py                   # CLI batch processor entry point
│   ├── data_loader.py            # CSV parsing & type coercion
│   ├── financial_engine.py       # Deterministic forecast & plan evaluator
│   ├── message_parser.py         # Message amendment detection
│   ├── ocr_extractor.py          # EasyOCR image amount extraction
│   ├── llm_client.py             # Groq/xAI API client + token tracking
│   ├── llm_advisor.py            # LLM explanation generator
│   └── evaluation/
│       └── usage_report.md       # Token usage & cost report
├── dataset/
│   ├── requests.csv              # 250 evaluation requests
│   ├── financial_profiles.csv    # User financial profiles
│   ├── financial_events.csv      # Transaction history
│   ├── exchange_rates.csv        # Fixed-date FX rates
│   ├── request_payment_options.csv
│   ├── messages.csv
│   ├── images.csv
│   └── output.csv                # ← Final predictions (250 rows)
├── DEPLOYMENT.md                 # HF Spaces deployment guide
└── AGENTS.md                     # Agent configuration & challenge rules
```

---

## 🧠 Key Design Decisions

### 1. Deterministic-First Architecture
All affordability decisions (safe amount, status, payment method, tie-breaking) are computed in pure Python with no LLM involvement. The LLM only writes the final explanation sentence. This guarantees:
- Zero financial hallucination
- Fully reproducible outputs
- Works even without an API key

### 2. Prompt Injection Defence
Messages and images are untrusted. All LLM calls use strict extraction schemas — the LLM extracts facts only and cannot modify the financial logic.

### 3. Conservative Forecasting
- Pending debits are reserved; pending credits are ignored until settled
- Recurring patterns only detected from historical evidence
- Balance never projected below `minimum_balance_to_keep`

---

## 📈 Evaluation Usage

See [`code/evaluation/usage_report.md`](code/evaluation/usage_report.md) for full token usage and cost breakdown.

---

## 🏆 Challenge

**HackerRank Orchestrate — September 2026**
Challenge: [Buy or Wait?](https://www.hackerrank.com/contests/hackerrank-orchestrate-september26/challenges/buy-or-wait)

---

## 📄 License

MIT
