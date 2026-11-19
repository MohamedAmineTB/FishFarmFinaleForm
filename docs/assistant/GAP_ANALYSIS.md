# Assistant gap analysis

**Before:** the approved prototype had a demo assistant: template answers computed in the browser from fake data, with
step chips, an inline chart, sources, an approval card and thumbs that only showed a toast. There was no back end, no
model, no tools, no storage and no evaluation.

**What the upgrade built** (CHATBOT_UPGRADE.md):

| Area | Built |
|---|---|
| Provider layer | `LLMProvider` with Anthropic (default `claude-haiku-5-5`, cached system prompt), OpenAI-compatible (Ollama) and a deterministic mock; automatic demo mode without a key |
| Agent loop | Hand-written: stream → tool call → execute → result → continue; 5 rounds, 800 output tokens, 2,000 input characters |
| Tools | 12 typed read tools + 2 approval-gated write tools; no owner-id argument; validation errors returned to the model |
| Security | `ai_reader` role, `ai` schema of `security_invoker` views, row-level security on `app.owner_id`, statement timeout, `<tool_data>` wrapping, escaped markdown, rate limits and token budget |
| Domain | `species_thresholds` with sources and `verified`; oxygen-saturation and un-ionized-ammonia helpers tested against published values |
| RAG | pgvector (when available), 11 cited notes, ingestion pipeline, hybrid search with Reciprocal Rank Fusion |
| Streaming & memory | SSE events (token, tool_call, tool_result, chart, source, approval_request, done, error), conversations and messages tables, rolling summary |
| Front end | The prototype's panel with real streaming, stop button, page-aware chips, charts, risk cards, comparisons, sources, data used, approvals, feedback, history |
| Quality | 44-case golden set, deterministic metrics in CI, `llm_requests` logging, AI Ops page, feedback |
| Smart features | Daily briefing, "Explain" buttons, sensor-health routing, what-if simulator, risk / comparison cards, emergency banner, proactive insight in Today's actions, FR/EN/AR with RTL, voice input, PDF export |

Not built, by choice: see `docs/DECISIONS.md` (assistant section).
