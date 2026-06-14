# CAS Email Engine — System Context

## Deployed services

- Email engine backend: https://cas-email-engine-backend-production-3b02.up.railway.app
- Outreach OS: https://cas-outreach-os-production.up.railway.app
- Dashboard: dashboard/index.html (open locally)
- Database: Supabase — https://tjpkmonazlqmbaazcker.supabase.co
- Email sending: Resend from kasper@casautomations.com (domain verified, eu-west-1)
- Reply detection: Gmail IMAP kaplelbackman@gmail.com (+ second inbox when configured)
- Lead sourcing: vet-intel GitHub Actions daily 08:00 Stockholm

## Current status as of 2026-06-14

- System fully operational — all known issues resolved
- Imports working (last vet-intel import 09:00 UTC 2026-06-14)
- 7 approved leads in queue, circuit ok, IMAP live
- **3-touch breakup sequence live:** initial (day 0) → FU1 (day 5) → breakup email (day 10)
  - Breakup: "Jag förstår om timing inte är rätt just nu." + one of two closing lines
  - After breakup: status = `sequence_complete`, re_engage_after = now+90d
  - PGRST205 fallback active until DB migration lands (status update still works)
  - DB migration auto-runs at startup via migrationService.js (Supabase pooler probe)
  - /api/test/status now shows `sequence_complete` count + `breakup_sent_7d`
- Sign-off rebranded to "Kasper, Drivverk AB" in all email prompts (initial, FU1, breakup)
- **Gothenburg active** — city flipped to active:true; sends fall back to default domain until SECOND_DOMAIN_FROM set
- SECOND_GMAIL_ADDRESS set in Railway (confirmed in /api/test/status), SECOND_GMAIL_APP_PASSWORD must also be set
- Instagram: 6 leads in DB (dm_sent), endpoint tested and working
- LinkedIn: 3 leads in DB, endpoint tested and working (saves to linkedin_leads table)
- Email greeting now personalized: "Hej Rebecca," when contact_name is set (extractFirstName handles multi-part legal names)
- Research prompt now asks for decision_maker_name (first name) from website + allabolag.se lookup

## Pain column architecture note

The leads table has NO pain-specific columns (primary_pain, pain_evidence, pain_source,
pain_score do not exist in the Supabase schema). All pain data lives in research_notes
JSON blob. DO NOT add these to INSERT/UPDATE payloads — PGRST205 blocks every write.

## New columns (pending DB migration)

`follow_up_2_sent_at` (timestamptz) and `re_engage_after` (timestamptz) are added by
migrationService.js at startup via Supabase pooler. Code has PGRST205 fallback so it
works before migration lands. Status flow: sent → sequence_complete (after breakup email).

## Architecture

- Node.js/Express on Railway (two services: email engine backend, outreach-os)
- Supabase (Postgres) via PostgREST and service_role JWT
- Anthropic claude-opus-4-7 for research + email generation (web_search tool)
- Anthropic claude-haiku-4-5-20251001 for follow-up generation (cheap/fast)
- Resend for email delivery (kasper@casautomations.com)
- node-cron scheduling with Europe/Stockholm timezone
- cities.js — single source of truth for multi-city routing config

## Send schedule

- Mon–Fri: 09:00, 10:00, 11:00, 14:00 Stockholm (4 slots/day × 5 days = 20/week capacity)
- DAILY_LIMIT = 4 (counts all outgoing emails: initial + follow-ups combined)
- Daily pipeline: 08:00 Mon-Fri Stockholm (research + generate for imported leads)
- Health check: every 6h UTC
- Daily summary: 18:00 Mon-Fri Stockholm
- IMAP poll: every 30 minutes (all configured inboxes in parallel)

## Key env vars (Railway — backend)

RESEND_API_KEY, ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_ANON_KEY,
SUPABASE_SERVICE_ROLE_KEY, BACKEND_API_KEY, GMAIL_ADDRESS,
GMAIL_APP_PASSWORD, REPLY_TO=cas@casautomations.com,
USE_VETINTEL_ONLY=true, GITHUB_TOKEN=(set in Railway — OAuth token with repo+workflow scope)

## Files to read before working

1. CONTEXT.md (this file)
2. backend/services/emailService.js
3. backend/services/healthAlertService.js
4. backend/services/schedulerService.js
5. backend/services/leadService.js
6. backend/services/resendService.js
7. backend/services/cities.js
8. outreach-os/server.js

Do not make changes until you have read the files listed above.
Tell me current state then ask what to work on.

## Multi-city activation — what to do manually when ready

See WARMUP.md for the full step-by-step and warmup schedule.
Short version of what you do manually (everything else is automated):

1. **Register domain** — casautomations.se (or chosen domain) at Loopia/Namecheap
2. **Create second Gmail** — new Google account + App Password (16 chars)
3. **Set 4 Railway env vars:**
   - SECOND_GMAIL_ADDRESS = new gmail address
   - SECOND_GMAIL_APP_PASSWORD = app password
   - SECOND_DOMAIN_FROM = Kasper <kasper@casautomations.se>
   - SECOND_DOMAIN_REPLY_TO = new gmail address
4. **Tell me** — I'll add the domain to Resend via API and verify DNS
5. **Flip city active in cities.js** — edit `gothenburg.active: false` → `true`, commit/push

That's it. All routing, IMAP polling, and warmup tracking is already built.
