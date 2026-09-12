# Buy or Wait? — AI Financial Decision Agent 💰

An intelligent, multi-layered financial decision agent developed for the **HackerRank Orchestrate** challenge. The system evaluates purchase and payment requests by reconstructing a user's true financial position, detecting recurring commitments, forecasting cash flows over a 90-day horizon, enforcing strict balance constraints, and generating human-friendly grounded explanations.

---

## 🚀 Key Features & Architecture

### 1. Deterministic Financial Safety Engine
- **Cash Flow Simulation**: Day-by-day account balance projection across a 90-day forecast horizon.
- **Conservative Accounting**: 
  - Reserves pending debits immediately.
  - Excludes pending credits, bonuses, commissions, and unrealized investment gains until confirmed settlement.
  - Confirmed salary counted only on settlement dates.
- **Strict Constraint Enforcement**: Guarantees account balance never falls below `minimum_balance_to_keep`.
- **Optimal Plan Tie-Breaking**:
  1. Complete full request on or before `desired_completion_date`
  2. Require zero spending reductions
  3. Minimize total payable cost
  4. Earliest payment start date
  5. Fewest payment installments
  6. Lowest `payment_option_id`

### 2. Prompt-Injection Defense Layer
- Isolates untrusted natural language evidence in transaction receipts and user messages.
- Deterministic regex and vision extraction extract structured numeric primitives (`amount`, `currency`, `due_date`) without following embedded instructions.

### 3. Hybrid Language Layer (Grok / LLM Advisor)
- Translates rigorous mathematical decisions into fluent, empathetic, and human-friendly financial explanations.
- Automatic fallback heuristics ensure 100% availability even offline.

---

## 📊 Visual Analytics Dashboard

An interactive dashboard (`dashboard.html`) is included for reviewing all 250 financial decisions, complete with status breakdown, payment plans, and grounded rationales.

---

## 🛠️ Quick Start & Usage

### Prerequisites
- Python 3.9+
- Recommended: Virtual environment (`venv` or `conda`)

### Installation
```bash
pip install -r code/requirements.txt
```

### Execution
Run the full financial pipeline across all requests:
```bash
python code/main.py
```

Outputs generated:
- `output.csv`: Complete evaluation results with all 8 contract columns.
- `code/evaluation/usage_report.md`: Itemized token usage, model calls, and financial analysis audit.

---

## 📁 Repository Structure

```text
├── code/
│   ├── main.py                  # CLI pipeline and orchestration
│   ├── financial_engine.py      # 90-day cash flow simulation and constraint checking
│   ├── data_loader.py           # Ingestion for profiles, events, options, rates
│   ├── llm_client.py            # LLM explanation generator and token tracker
│   ├── ocr_extractor.py         # Receipt image parser & injection defense
│   ├── message_parser.py        # Message parser & event link resolver
│   ├── requirements.txt         # Dependencies
│   └── evaluation/
│       └── usage_report.md      # Token and cost audit report
├── dataset/                     # Financial datasets and media evidence
├── dashboard.html               # Visual decision dashboard
├── output.csv                   # Validated evaluation predictions
└── code.zip                     # Submission package
```

---

## 📄 Output Specification

The agent outputs `output.csv` with the following 8 standardized columns:
- `request_id`
- `amount_safe_to_pay`
- `affordability_status` (`affordable_now`, `affordable_with_plan`, `affordable_later`, `not_affordable`)
- `recommended_payment_method` (`full_payment`, `partial_payment`, `installments`, `wait`, `not_recommended`)
- `payment_plan`
- `earliest_date_for_full_payment`
- `spending_changes_needed`
- `decision_explanation`
