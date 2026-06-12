# CAS Email Engine — System Context

## Deployed services

- Email engine backend: https://cas-email-engine-backend-production-3b02.up.railway.app
- Outreach OS: https://cas-outreach-os-production.up.railway.app
- Dashboard: dashboard/index.html (open locally)
- Database: Supabase — https://tjpkmonazlqmbaazcker.supabase.co
- Email sending: Resend from kasper@casautomations.com
- Reply detection: Gmail IMAP kaplelbackman@gmail.com
- Lead sourcing: vet-intel GitHub Actions daily 08:00 Stockholm

## Current status as of 2026-06-12

- 18 approved leads in queue, 9 sent, 0 warm leads
- Email sends working — last sent huddingezoo@hotmail.com 2026-06-11 08:00 UTC
- Duplicate send mutex deployed 2026-06-11 13:38 (global _sendInProgress flag)
- Health check every 6h with 2-consecutive-check persistence gate
- Follow-up sequence fixed: vet-intel leads now receive follow-ups (opted_out NULL handled)
- Follow-up prompt now personalised: includes original subject, body, primary_pain, pain_evidence
- Open tracking enabled on all Resend sends
- List-Unsubscribe header added to all sends (RFC 8058 compliant)
- USE_VETINTEL_ONLY=true — pipeline researches imported leads only

## Known issues requiring action

- system_state table missing from Supabase
  → State (circuit breaker, last_import_at, imap timestamps) resets on restart
  → Fix: run POST /api/admin/run-migration with BACKEND_API_KEY header

- GITHUB_TOKEN env var in Railway is expired
  → Health check GitHub Actions call returns 404, no_import_48h alert always fires
  → Fix: generate a new PAT at github.com/settings/tokens, update in Railway env vars

- X-Forwarded-For ValidationError in outreach-os logs
  → Add app.set('trust proxy', 1) to outreach-os/server.js

## Pain column architecture note

The leads table has NO pain-specific columns (primary_pain, pain_evidence, pain_source,
pain_score do not exist in the Supabase schema). All pain data lives in research_notes
JSON blob. Email and follow-up prompts read from research_notes directly. DO NOT add
these columns to INSERT/UPDATE payloads — PGRST205 will block every write.

## Architecture

- Node.js/Express on Railway (two services: email engine backend, outreach-os)
- Supabase (Postgres) via PostgREST and service_role JWT
- Anthropic claude-opus-4-7 for research + email generation (web_search tool)
- Anthropic claude-haiku-4-5-20251001 for follow-up generation (cheap/fast)
- Resend for email delivery (kasper@casautomations.com)
- node-cron scheduling with Europe/Stockholm timezone

## Send schedule

- Tue/Wed/Thu: 09:00, 10:00, 11:00 Stockholm
- Mon/Fri: 10:00 Stockholm
- Daily pipeline: 08:00 Mon-Fri Stockholm (research + generate for imported leads)
- Health check: every 6h UTC
- Daily summary: 18:00 Mon-Fri Stockholm
- IMAP poll: every 30 minutes

## Key env vars (Railway)

RESEND_API_KEY, ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_ANON_KEY,
SUPABASE_SERVICE_ROLE_KEY, BACKEND_API_KEY, GMAIL_ADDRESS,
GMAIL_APP_PASSWORD, REPLY_TO=cas@casautomations.com,
USE_VETINTEL_ONLY=true, GITHUB_TOKEN (expired — needs renewal)

## Files to read before working

1. CONTEXT.md (this file)
2. backend/services/emailService.js
3. backend/services/healthAlertService.js
4. backend/services/schedulerService.js
5. backend/services/leadService.js
6. backend/services/resendService.js
7. outreach-os/server.js

Do not make changes until you have read the files listed above.
Tell me current state then ask what to work on.
