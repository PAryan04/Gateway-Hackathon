# AI-Chatbot — GATEWAY Hackathon

This repository contains the **FRONTLINE** project built for the GATEWAY Hackathon.

---

## Project: FRONTLINE — AI-Powered Customer Message Triage

> An end-to-end triage pipeline that reads raw customer support messages in any format  
> and classifies each one into a structured JSON decision — reliably, instantly, and for free.

**Powered by:** Google Gemini 2.0 Flash (free tier) · Python · Rich CLI

---

## Repository Structure

```
AI-chatbot/
└── frontline-triage/       ← The main project lives here
    ├── ingestion.py
    ├── triage_engine.py
    ├── guardrails.py
    ├── evaluate.py
    ├── dashboard.py
    ├── main.py
    ├── requirements.txt
    ├── .env.example
    ├── README.md           ← Full setup & usage guide
    └── data/
        ├── dummy_messages.json
        └── ground_truth.json
```

---

## Quick Start

```bash
cd frontline-triage
pip install -r requirements.txt

# Get a free Gemini API key at: https://aistudio.google.com/app/apikey
copy .env.example .env    # then edit .env and add your key

python main.py            # Run the CLI dashboard
python main.py --evaluate # Run accuracy evaluation

# Run the Web-Based Dashboard & Playground
python web_server.py      # Opens on http://localhost:8000
```

For full setup instructions, see [frontline-triage/README.md](frontline-triage/README.md).