# Evaluation Usage Report

## HackerRank Orchestrate (September 2026) — Buy or Wait?

### 1. Model & System Overview
- **Architecture**: Hybrid Deterministic Engine + Grok/Compatible LLM
- **Provider**: Groq Cloud
- **Extraction Model (Images & Messages)**: `groq/compound-mini`
- **Generation Model (Decision Explanations)**: `groq/compound-mini`

### 2. Token & Cost Summary (Full Dataset Run)

| Metric | Total | Average Per Request (N=250) |
|---|---|---|
| **Total Model Calls** | 122 | 0.49 calls/req |
| **Input (Prompt) Tokens** | 100,108 | 400.4 tokens/req |
| **Output (Completion) Tokens** | 35,006 | 140.0 tokens/req |
| **Total Tokens** | 135,114 | 540.5 tokens/req |
| **Estimated Cost (USD)** | $0.007806 | $0.000031 / req |

### 3. Call Breakdown by Sub-Task

| Task | Calls | Total Tokens | Sub-Task Focus |
|---|---|---|---|
| **Image Amount Extraction** | 0 | 0 | Vision extraction with local OCR fallback |
| **Message Interpretation** | 0 | 0 | JSON-structured financial fact extraction |
| **Decision Explanation Generation** | 122 | 135,114 | Grounded plain-language rationale generation |

### 4. Integrity & Constraints
- **Zero Hallucination Guarantee**: All financial evaluations (affordability status, safe amount, payment plan, tie-break ranking) were computed strictly deterministically in Python.
- **Prompt Injection Defense**: Untrusted text from user messages and image labels was isolated to strict extraction schemas with local validation.
