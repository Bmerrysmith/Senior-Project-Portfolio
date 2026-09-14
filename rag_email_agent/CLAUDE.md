# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

A RAG-based email agent that connects to a personal Outlook account, indexes
email content for retrieval, and sends the user a daily digest email
summarizing and triaging that day's messages by urgency.

## Stack

- **Language / framework:** Python, Flask
- **Database:** Postgres with `pgvector` for embedding storage/similarity search
- **Email source:** Microsoft Graph API via MSAL (personal Microsoft/Outlook
  account — not a work/org account)
- **Scope:** `Mail.Read` + `Mail.Send` — read access plus the ability to send
  a digest email back to the user. No `Mail.ReadWrite` (no flag/move/modify
  needed). No sending to anyone other than the user's own address.
- **Mail provider:** built directly against Graph API, no provider-abstraction
  layer (single provider for v1 — see PLANNING.md decision log)

## Build Order

Work proceeds in phases; do not jump ahead of the current phase without discussion.

1. **OAuth + basic fetch** _(done)_ — MSAL auth flow, fetch/list
   messages read-only, confirm auth + basic Graph API access works end to end.
2. **Chunk + embed emails** _(done)_ — parsing/cleaning email content,
   chunking strategy, generating embeddings, storing in Postgres/pgvector.
3. **Retrieval + summarization/triage** _(done)_ — semantic search over
   embedded emails, summarization, urgency grading.
4. **Daily digest dispatch** _(done)_ — compose a summary of the day's
   emails (grounded in retrieved context) and send it to the user's own
   inbox via `Mail.Send`. Self-send only, hardcoded recipient.
5. **Automation + guardrails** _(done)_ — full pipeline runs unattended on
   AWS Lambda (`rag-email-agent-daily`, container image) via EventBridge
   Scheduler at 7 AM ET. DB is Supabase (session pooler); all secrets in
   AWS Secrets Manager. Idempotency via `digest_log` / `triage_runs`;
   failure signal is an in-handler Graph email + Scheduler retry. See the
   2026-08-28 PLANNING.md entries and `deploy/deploy.md`.

## Daily Pipeline (target end state)

1. Fetch all emails received that day
2. Retrieve related context from pgvector (past emails/threads/summaries)
3. Summarize + grade urgency, grounded in retrieved context
4. Persist: chunk + embed today's emails + summaries into pgvector
5. Dispatch: send digest to self via `Mail.Send`

Scheduling: local cron (or OS task scheduler) during development. Cloud
scheduling (e.g. EventBridge + Lambda) is a later consideration once the
pipeline is stable — not before.

## Current Status

Steps 1 through 5 are done and confirmed working end-to-end. The pipeline
runs unattended on AWS Lambda + EventBridge Scheduler (7 AM ET daily)
against Supabase, with secrets in AWS Secrets Manager. A scheduled run has
been observed firing and completing, and real digests have been sent via
Graph. Redeploy/runbook: `deploy/deploy.md`. Remaining work is small
follow-ups only (see the 2026-08-28 PLANNING.md entry).

## Working Conventions

- Do not widen Graph API scopes beyond `Mail.Read` + `Mail.Send` without
  flagging it.
- Keep phases isolated — avoid pulling in step 2+ concerns (chunking,
  embeddings, dispatch) while still building step 1.
- Before writing or modifying any code, propose a plan in PLANNING.md (or
  update the relevant section) and wait for explicit approval. Do not
  implement until confirmed.
- Record non-obvious design decisions in [PLANNING.md](PLANNING.md) as
  they're made, rather than leaving them implicit in code.
- Never commit OAuth credentials, tokens, or `.env` files.
