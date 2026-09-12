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
| **Total Model Calls** | 2 | 0.01 calls/req |
| **Input (Prompt) Tokens** | 2,378 | 9.5 tokens/req |
| **Output (Completion) Tokens** | 674 | 2.7 tokens/req |
| **Total Tokens** | 3,052 | 12.2 tokens/req |
| **Estimated Cost (USD)** | $0.000173 | $0.000001 / req |

### 3. Call Breakdown by Sub-Task

| Task | Calls | Total Tokens | Sub-Task Focus |
|---|---|---|---|
| **Image Amount Extraction** | 0 | 0 | Vision extraction with local OCR fallback |
| **Message Interpretation** | 0 | 0 | JSON-structured financial fact extraction |
| **Decision Explanation Generation** | 2 | 3,052 | Grounded plain-language rationale generation |

### 4. Integrity & Constraints
- **Zero Hallucination Guarantee**: All financial evaluations (affordability status, safe amount, payment plan, tie-break ranking) were computed strictly deterministically in Python.
- **Prompt Injection Defense**: Untrusted text from user messages and image labels was isolated to strict extraction schemas with local validation.
