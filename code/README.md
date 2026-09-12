# Buy or Wait? — AI Financial Decision Agent

## HackerRank Orchestrate Challenge Submission

### Overview
This package contains the complete solution for the **Buy or Wait?** financial decision agent challenge. The system evaluates purchase and payment requests by reconstructing each user's financial position, detecting recurring commitments, forecasting cash flows over a conservative 90-day period, enforcing minimum balance constraints, and generating grounded explanations.

---

### Key Architectural Highlights

1. **Deterministic Financial Safety Engine (`financial_engine.py`)**:
   - **Cash Flow Simulation**: Models day-by-day account balances across the 90-day forecast horizon.
   - **Constraint Enforcement**: Guarantees that account balances never drop below `minimum_balance_to_keep`.
   - **Prudent Accounting**: Reserves pending debits immediately; ignores pending credits, bonuses, and investment gains until settled; and counts salary only on confirmed settlement dates.
   - **Exact Tie-Break Ranking**:
     1. Complete full request by `desired_completion_date`
     2. Require no spending changes
     3. Minimize total payable amount
     4. Start payment earlier
     5. Use fewer payments
     6. Lowest `payment_option_id`

2. **Prompt-Injection Defense (`ocr_extractor.py`, `message_parser.py`)**:
   - Isolates all untrusted text from messages and image evidence.
   - Vision and message extraction modules extract strictly structured JSON primitives (`amount`, `currency`, `action`), completely ignoring adversarial natural language instructions.

3. **Hybrid Language Layer (`llm_client.py`)**:
   - Uses Grok / OpenAI-compatible API to generate plain-language, empathetic financial rationale grounded strictly in computed facts.
   - Includes automatic fallback templates if the API is offline or unconfigured.

---

### Project Structure

```text
code/
├── main.py                  # Main entry point orchestrating data load, evaluation, and output
├── financial_engine.py      # Core deterministic financial math, forecasting, and plan ranking
├── llm_client.py            # LLM advisor for decision explanations and token accounting
├── data_loader.py           # Dataset ingestion and strict type parsing
├── message_parser.py        # Financial message parsing and event amendment logic
├── ocr_extractor.py         # Numeric amount extractor with verified OCR baseline
├── requirements.txt         # Minimal Python dependencies (pandas, Pillow)
└── evaluation/
    ├── usage_report.md      # Itemized token usage, model metrics, and cost breakdown
    └── main.py              # Auxiliary evaluation script
```

---

### Setup & Execution Instructions

#### 1. Requirements
- Python 3.10+
- Install dependencies:
  ```bash
  pip install -r requirements.txt
  ```

#### 2. Configuration (Optional)
The pipeline is fully operational in standalone deterministic mode ($0.00 cost). To enable live LLM-generated explanations, configure your API key:
```bash
# Windows PowerShell
$env:GROK_API_KEY = "your-api-key"

# Linux / macOS
export GROK_API_KEY="your-api-key"
```

#### 3. Run the Agent
From the project root:
```bash
python code/main.py
```
This reads from `dataset/` and generates:
- `dataset/output.csv` (and `output.csv` at repository root)
- `code/evaluation/usage_report.md` (updated token and cost report)
