# FRONTLINE — AI-Powered Customer Message Triage System

> Production-grade, injection-resistant, multi-format AI triage pipeline  
> Built with Google Gemini 2.0 Flash · Python · Rich CLI · **100% Free API**

---

## What it does

FRONTLINE reads raw customer support messages in **any format** (plain text, HTML, JSON, PDF, CSV), classifies each one using Google Gemini AI, and outputs a structured JSON decision:

```json
{
  "category": "billing",
  "priority": "P1",
  "summary": "Customer reports unauthorized charge and requests immediate refund.",
  "suggested_action": "Review payment records. Issue refund if confirmed. Escalate to billing team.",
  "needs_human": true,
  "confidence": 0.91,
  "language_detected": "en",
  "input_format_detected": "text"
}
```

---

## Architecture

```
Raw Input (any format)
        │
        ▼
┌─────────────────────┐
│   ingestion.py      │  ← Detect format, extract clean text, handle encoding
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  triage_engine.py   │  ← Call Gemini API with injection-resistant XML prompt
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│   guardrails.py     │  ← Validate JSON schema, enforce human-escalation rules
└─────────────────────┘
        │
   ┌────┴────┐
   ▼         ▼
dashboard  evaluate
 .py        .py
```

---

## File Structure

```
frontline-triage/
├── ingestion.py          ← Multi-format input layer (text/HTML/JSON/PDF/CSV)
├── triage_engine.py      ← Gemini API integration + injection-resistant prompt
├── guardrails.py         ← Schema validation, escalation rules, failure logging
├── evaluate.py           ← Accuracy, cost & latency evaluation module
├── dashboard.py          ← Rich CLI table dashboard
├── main.py               ← Entry point — ties everything together
├── requirements.txt      ← All dependencies with minimum versions
├── .env.example          ← Copy to .env and add your API key
└── data/
    ├── dummy_messages.json  ← 40 diverse test messages
    └── ground_truth.json    ← 10 hand-labeled messages for evaluation
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Get your FREE Gemini API key

1. Go to **https://aistudio.google.com/app/apikey**
2. Sign in with your Google account
3. Click **"Create API key"**
4. Copy the key (starts with `AIza...`)
5. Create a `.env` file:

```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

6. Open `.env` and replace `your_key_here` with your actual key:

```
GEMINI_API_KEY=AIzaSy...
```

Or set it directly in your terminal:

```powershell
# Windows PowerShell
$env:GEMINI_API_KEY = "AIza..."

# Linux / macOS
export GEMINI_API_KEY="AIza..."
```

### 3. Run the dashboard

```bash
# Process all 40 dummy messages
python main.py

# Process only the first 10
python main.py --limit 10

# Show suggested actions for urgent messages
python main.py --actions

# Save results to JSON
python main.py --save results.json
```

### 4. Triage a single message

```bash
python main.py --single "I was charged twice this month for my subscription!"
```

### 5. Run the evaluation

```bash
python main.py --evaluate
```

---

## Usage Reference

```
python main.py [OPTIONS]

Options:
  --input, -i PATH       Path to messages JSON or directory [default: data/dummy_messages.json]
  --limit, -n N          Process only first N messages
  --evaluate, -e         Run accuracy evaluation against ground truth
  --single, -s TEXT      Triage a single message inline
  --save PATH            Save triage results to JSON file
  --actions, -a          Show suggested action panels for urgent messages
  --no-env-check         Skip API key check

Environment:
  GEMINI_API_KEY         Required: Your Google Gemini API key (free at aistudio.google.com)
  LOG_LEVEL              Optional: DEBUG | INFO | WARNING | ERROR [default: WARNING]
```

---

## Output JSON Schema

| Field                  | Type    | Description                                          |
|------------------------|---------|------------------------------------------------------|
| `category`             | string  | billing, technical, account, security, complaint, general, out-of-scope, gibberish |
| `priority`             | string  | P0 (critical) → P3 (low)                            |
| `summary`              | string  | 1-2 sentence summary of the issue                    |
| `suggested_action`     | string  | Recommended action for the support team              |
| `needs_human`          | boolean | Whether a human agent must review this               |
| `confidence`           | float   | 0.0–1.0 classification confidence                   |
| `language_detected`    | string  | ISO 639-1 code (en, hi, fr, etc.)                   |
| `input_format_detected`| string  | text, html, json, pdf, other                        |

### Priority Scale

| Priority | Meaning             | Examples                                       |
|----------|---------------------|------------------------------------------------|
| P0       | CRITICAL            | System down, revenue loss, data breach          |
| P1       | HIGH                | Billing fraud, account suspended, many users   |
| P2       | MEDIUM              | Single user issue, billing discrepancy         |
| P3       | LOW                 | General questions, feedback, out-of-scope      |

---

## Security Design

FRONTLINE uses **XML delimiter isolation** to prevent prompt injection:

```
SYSTEM PROMPT: [strict triage instructions]

USER MESSAGE:
<customer_message format="text">
  [ANY content the user sends, treated as DATA not instructions]
</customer_message>
```

Additionally:
- Client-side regex pre-screening for 9 injection patterns
- Automatic flagging: `category=security`, `needs_human=true`, `confidence≤0.35`
- All injection attempts are logged in the failure log

---

## Free Tier Limits (Gemini 2.0 Flash)

| Metric                  | Free Tier Limit          |
|-------------------------|--------------------------|
| Requests per minute     | 15 RPM                   |
| Tokens per minute       | 1,000,000 TPM            |
| Requests per day        | 1,500 RPD                |
| Cost                    | **$0.00**                |

> For higher throughput, upgrade to a paid Gemini plan at https://ai.google.dev/gemini-api/docs/pricing

---

## Test Dataset Coverage (40 messages)

| ID       | Type                              |
|----------|-----------------------------------|
| msg_001  | Clear billing complaint           |
| msg_002  | Vague/ambiguous ("it's broken")   |
| msg_003  | Angry rant with frustration       |
| msg_004  | Multi-issue (billing + tech + UX) |
| msg_005  | Sarcastic message                 |
| msg_006  | Out-of-scope (pizza recipe)       |
| msg_007  | Hindi language message            |
| msg_008  | Prompt injection attempt          |
| msg_009  | Gibberish input                   |
| msg_010  | Empty string                      |
| msg_011  | HTML-formatted message            |
| msg_012  | JSON-formatted message            |
| msg_013  | Very long enterprise complaint    |
| msg_014  | No punctuation, all lowercase     |
| msg_015  | P0 emergency (system down)        |
| msg_016  | French language                   |
| msg_017  | Pricing inquiry                   |
| msg_018  | Technical API/OAuth issue         |
| msg_019  | Cancellation request              |
| msg_020  | Spanish billing issue             |
| msg_021  | Prompt injection (admin override) |
| msg_022  | 2FA technical issue               |
| msg_023  | Casual/dismissive message         |
| msg_024  | Out-of-scope (ML question)        |
| msg_025  | Security breach (HTML formatted)  |
| msg_026  | JSON with angry refund request    |
| msg_027  | Minimal / ambiguous request       |
| msg_028  | API rate limit discrepancy        |
| msg_029  | German language                   |
| msg_030  | Garbled/encoding error text       |
| msg_031  | Unauthorized payment dispute      |
| msg_032  | AI hallucination complaint        |
| msg_033  | Automated webhook ping (JSON)     |
| msg_034  | Data export / churn request       |
| msg_035  | Emergency data recovery           |
| msg_036  | Positive feedback / compliment    |
| msg_037  | DAN-style jailbreak attempt       |
| msg_038  | Whitespace-only input             |
| msg_039  | Account suspension, no warning    |
| msg_040  | Trivial out-of-scope (math)       |

---

## Evaluation Metrics

The `evaluate.py` module reports:
- **Category accuracy %** — did we get the right category?
- **Priority accuracy %** — did we assign the right urgency?
- **Needs-human accuracy %** — did we correctly flag for human review?
- **Full match %** — all three fields correct
- **Avg tokens/message** — for usage tracking
- **Avg latency/message** — for SLA planning
- **Failure log** — every case where guardrails had to intervene

---

## Troubleshooting

**`GEMINI_API_KEY not set`**  
→ Create a `.env` file from `.env.example` and add your key from https://aistudio.google.com/app/apikey

**`ModuleNotFoundError: google.generativeai`**  
→ Run `pip install -r requirements.txt`

**`pdfplumber not installed`**  
→ Run `pip install pdfplumber` if you need PDF support.

**`RESOURCE_EXHAUSTED` / rate limit error**  
→ You've hit the free tier limit (15 RPM). Add a small delay between messages, or use `--limit` to process fewer at once.

**LLM returns non-JSON**  
→ The guardrails layer will automatically retry with a stricter prompt, then fall back to a safe default JSON. Check the failure log.

---

## Development Notes

- **Never commit `.env`** — it's in `.gitignore` already
- Run `LOG_LEVEL=DEBUG python main.py` for verbose pipeline logs
- The `_meta` field in results contains token counts and latency (internal use only)
- The guardrails layer applies rules **after** the LLM responds — LLM decisions can be overridden
