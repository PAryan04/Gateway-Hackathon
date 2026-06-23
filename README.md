# FRONTLINE — AI Decisions Submission Note

## Model + Tools Used
- **Primary LLM**: Google Gemini 2.0 Flash (`gemini-2.0-flash`). Chosen for its zero-cost free tier (15 requests/min, 1,500 requests/day), exceptional speed, and native support for structured JSON schema enforcement.
- **Fallback LLM**: Groq Cloud running Llama 3.3 70B (`llama-3.3-70b-versatile`). Chosen as a secondary high-performance API to step in automatically via cascade routing when Gemini credentials or rate limits fail.
- **Final Fallback**: An offline, rule-based local classifier that guarantees structured JSON output at zero cost, ensuring high system uptime during complete network or API failure.
- **Libraries**:
  - `pdfplumber` for structured text and layout extraction from PDF customer tickets.
  - `chardet` for automatic character-encoding detection of raw files, preventing ingestion errors.
  - `rich` for formatting terminal output and pipeline diagnostics in real-time.
  - `python-dotenv` for loading secrets from local environment files, maintaining security compliance.

## Prompt Strategy
- **XML Tag Isolation**: The system wraps customer ticket content inside `<customer_message>` and `</customer_message>` XML tags. The system prompt directs the LLM to treat content inside these tags exclusively as data to be classified, neutralising any instruction overrides or jailbreak directives.
- **JSON Enforcement**: Configured natively using `response_mime_type="application/json"` with Gemini. For Groq/Llama, the prompt explicitly demands raw JSON, and the engine uses regular expression block extraction (`re.search(r"\{.*\}", ...)`) followed by `json.loads` parsing to ensure output compliance.
- **Alternative Comparison**: This design is chosen over plain text string interpolation because XML tags create a distinct boundary that LLMs recognize as data-only zones, significantly reducing classification drift and prompt injection success rates.

## Handling Uncertainty and Bad Input
- **Gibberish and Empty Input**: Input length checks instantly catch empty tickets. Incomprehensible inputs are caught via rule-based heuristics and LLM scoring, classifying them as `gibberish` or `out-of-scope` with a low confidence score (`<=0.15`).
- **Non-English Input**: The LLM identifies the ticket's ISO 639-1 language code. Any message flagged with a non-English code has its `needs_human` flag overridden to `True` to prevent translation and context errors.
- **Multi-Issue Cues**: A local keyword rule parses tickets for multiple transition words (e.g., "also", "additionally", "another issue"). If multiple cues trigger, `needs_human` is forced to `True` for manual triage.
- **Prompt Injection & Security threats**: Standardized regex matches (e.g., "ignore previous instructions") run against the input. If flagged by regex, or if the LLM categorizes the message under `security`, confidence is restricted to `<=0.35` and `needs_human=True` is enforced.
- **Uncertainty Escalation**: Post-triage guardrails automatically force `needs_human` to `True` for any ticket scoring low confidence (`<0.60`) or high-priority threats (`P0` or `P1`).

## Evaluation and Validation
- **Evaluation Module**: Supported by `evaluate.py` which runs live inputs against `data/ground_truth.json`, a hand-labeled dataset representing edge-cases, multi-issues, billing complaints, and prompt injections.
- **Metrics Tracked**: Accuracy (category, priority, needs_human, and perfect-match percentage), execution latency, token counts, and transaction cost in USD.
- **Evaluation Performance**: Running under Groq fallback (due to active Gemini API key validation constraints), the system achieves:
  - **Category Accuracy**: 80.0%
  - **Priority Accuracy**: 90.0%
  - **Needs-Human Accuracy**: 80.0%
  - **Perfect Match Accuracy**: 70.0%
  - **Average Latency**: 1.12 seconds per ticket.
- **Failure Modes**:
  1. *Gibberish Inconsistencies*: The LLM flags empty/random text (`msg_009`, `msg_010`) as `gibberish` and sets `needs_human=True` due to low confidence, whereas the ground truth expects `general` with `needs_human=False`.
  2. *Priority Disagreements*: Complex complaints (`msg_031` - billing dispute after a free trial) are triaged as medium-urgency (`P2`) by Llama instead of high-urgency (`P1`).

## Future Improvements
- **Local Pre-Routing Classifier**: Build a fast keyword or embedding-based vector search classifier to intercept empty, duplicate, or out-of-scope tickets locally before they consume LLM API tokens.
- **Dynamic Few-Shot Injection**: Implement a vector database (e.g., FAISS) to dynamically retrieve 2-3 similar triaged tickets and append them as few-shot examples in the system prompt, resolving edge-case priority mismatches.
- **Sub-Issue Decomposition**: Upgrade the pipeline to handle multi-issue tickets by breaking them into separate sub-queries, running parallel classifications, and joining the results into a single composite decision.