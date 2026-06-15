# CAS Email Engine — System Context

## Deployed services

- Email engine backend: https://cas-email-engine-backend-production-3b02.up.railway.app
- Outreach OS: https://cas-outreach-os-production.up.railway.app
- Dashboard: dashboard/index.html (open locally)
- Database: Supabase — https://tjpkmonazlqmbaazcker.supabase.co
- Email sending: Resend from kasper@casautomations.com (domain verified, eu-west-1)
- Reply detection: Gmail IMAP kaplelbackman@gmail.com (+ second inbox when configured)
- Lead sourcing: vet-intel GitHub Actions daily 08:00 Stockholm

## Current status as of 2026-06-15

### System health
- Send cycle RESTORED — was broken June 12–15 due to DB constraint issue (see below)
- 6 approved leads in queue, will send at 09/10/11/14 Stockholm Mon–Fri
- Anthropic credits EXHAUSTED — email generation + Instagram/LinkedIn find blocked
- IMAP live (polls every 30 min), circuit ok, vet-intel import running daily
- Railway deploy: commit `ff469e2` (vet-intel: `2bc1cc9`)

### Critical: Anthropic credits
- API returns "credit balance too low" — no new emails can be generated
- Existing 6 approved leads will SEND fine (content already generated)
- After queue drains, pipeline stops until credits are topped up
- Action needed: top up at https://console.anthropic.com/billing

### Critical: DB constraint fix needed (Supabase SQL Editor)
- The leads_status_check constraint is missing: 'bounced', 'out_of_office', 'sequence_complete'
- The sent_log_type_check constraint is missing: 'followup_1', 'followup_2'
- Current workaround: replaced 'sending' lock with in-process mutex (ff469e2)
- Permanent fix: run this SQL at https://supabase.com/dashboard/project/tjpkmonazlqmbaazcker/sql
  ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_status_check;
  ALTER TABLE leads ADD CONSTRAINT leads_status_check CHECK (status IN (
    'new','generated','approved','skipped','sending','sent',
    'no_response','bounced','opted_out','warm','out_of_office','sequence_complete'
  ));
  ALTER TABLE sent_log DROP CONSTRAINT IF EXISTS sent_log_type_check;
  ALTER TABLE sent_log ADD CONSTRAINT sent_log_type_check CHECK (type IN (
    'initial','followup','followup_1','followup_2'
  ));

### Email sequence (3-touch)
- **Initial (day 0):** DISCOVERY style — asks an open question about their operational pain. No solution pitch. (Changed 2026-06-14)
- **Follow-up (day 5):** Solution-oriented, references research_notes pain signal, "Fortfarande värt en titt?"
- **Breakup (day 10):** "Jag förstår om timing inte är rätt just nu." + one of two closing lines
- After breakup: status = `sequence_complete`, re_engage_after = now+90d
- PGRST205 fallback active (migrationService.js adds columns at startup via Supabase pooler probe)
- /api/test/status shows `sequence_complete` count + `breakup_sent_7d`

### Sign-off (all 3 emails)
`Kasper, Drivverk AB` (rebranded from CAS Automations, applies to initial + FU1 + breakup)

### Email personalization
- Greeting: "Hej Rebecca," when contact_name is set (extractFirstName handles multi-part names)
- Research prompt asks for decision_maker_name from website + allabolag.se lookup

### Clearout email verification
- Active — CLEAROUT_API_KEY set in Railway
- Leads where Clearout returns safe_to_send=false are skipped and marked with skip_reason in research_notes

### vet-intel SEND filter (as of last vet-intel session)
- Score threshold lowered to ≥ 45 (was ≥ 60) to capture more clinics
- Medium-signal leads included (was hard-filtered out)
- QUEUE bucket eliminated — all leads go directly to SEND or IGNORE
- Gothenburg queries added to settings.py (2026-06-14: now API-driven, see City Rotation below)

### Social outreach
- Instagram: 6 leads in DB (dm_sent), endpoint tested and working
- LinkedIn: 3 leads in DB, endpoint tested and working (saves to linkedin_leads table)

## City rotation framework (live as of 2026-06-14)

### How it works
- **20 Swedish cities** defined in cities.js (Stockholm → Sundsvall in population order)
- **Currently active:** Stockholm + Gothenburg (18 others queued inactive)
- vet-intel calls `GET /api/cities/next` at start of each run → gets target city + Google Maps queries
- vet-intel calls `POST /api/cities/complete-run` with `{city, leads_found}` after push
- **Exhaustion rule:** 3 consecutive zero-lead runs → city marked exhausted
- When ALL active cities are exhausted → next inactive city auto-activates (no manual step needed)
- State persisted in `system_state` Supabase table under key `city_rotation_state`

### Endpoints
- `GET  /api/cities/next`         — vet-intel: get current target city + queries
- `POST /api/cities/complete-run` — vet-intel: report leads found this run
- `GET  /api/cities/status`       — dashboard: all 20 cities, active/exhausted/totals

### City order (rotation queue)
Stockholm → Gothenburg → Malmö → Uppsala → Linköping → Örebro → Västerås → Helsingborg →
Norrköping → Jönköping → Lund → Umeå → Gävle → Borås → Eskilstuna → Södertälje →
Karlstad → Växjö → Halmstad → Sundsvall

### Email routing for new cities
New cities use Stockholm credentials (kasper@casautomations.com) until a dedicated
domain + Gmail is set in Railway per WARMUP.md. No manual step needed to route emails —
getCityForLead() matches by area string automatically.

## Email strategy detail

### Initial email (discovery, day 0)
- LINE 1: Clinic-specific hook — structural (website signal) or review-based or fallback
- LINES 2-3: Open discovery question about which operational area feels heaviest
  - Examples: "Vad tar mest tid av det administrativa just nu — samtal, bokningar, eller uppföljning?"
  - No product. No "Vi löser det". No CTA beyond the question itself.
- Sign-off: `Kasper, Drivverk AB`
- Footer: `Vill du inte bli kontaktad igen? Svara bara på det här mejlet.`

### Follow-up (solution pitch, day 5)
- 2 lines before sign-off
- Reframes around what they are LOSING (missed bookings, clients going elsewhere)
- Ends with: "Fortfarande värt en titt?"
- Generated per-lead using claude-haiku-4-5-20251001, references research_notes pain signal

### Breakup (final, day 10)
- 2 lines before sign-off
- Line 1 (exact): "Jag förstår om timing inte är rätt just nu."
- Line 2: "Vill du att jag hör av mig igen om 2-3 månader istället?" OR "Om det är något specifikt som inte stämde, säg gärna till — annars hör jag inte av mig mer."

### Warm lead reply flow
- Any reply to the discovery email is captured in `warm_lead_reply`
- If the reply describes a real problem → Kasper's cue for a manual tailored response
- Automated sequence stops at warm_lead = true (no automated pitch follows)

## Pain column architecture note

The leads table has NO pain-specific columns (primary_pain, pain_evidence, pain_source,
pain_score do not exist in the Supabase schema). All pain data lives in research_notes
JSON blob. DO NOT add these to INSERT/UPDATE payloads — PGRST205 blocks every write.

## New columns (added by migrationService.js at startup)

`follow_up_2_sent_at` (timestamptz) and `re_engage_after` (timestamptz) are added via
Supabase pooler. Code has PGRST205 fallback so it works before migration lands.

## Architecture

- Node.js/Express on Railway (two services: email engine backend, outreach-os)
- Supabase (Postgres) via PostgREST and service_role JWT
- Anthropic claude-opus-4-7 for research + email generation (web_search tool)
- Anthropic claude-haiku-4-5-20251001 for follow-up + breakup generation (cheap/fast)
- Resend for email delivery (kasper@casautomations.com)
- node-cron scheduling with Europe/Stockholm timezone
- cities.js — 20-city config with areas[] + queries[] per city
- cityRotationService.js — rotation state, exhaustion tracking, auto-activation

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
USE_VETINTEL_ONLY=true, GITHUB_TOKEN=(set in Railway — OAuth token with repo+workflow scope),
CLEAROUT_API_KEY=(set in Railway)

## Files to read before working

1. CONTEXT.md (this file)
2. backend/services/emailService.js
3. backend/services/healthAlertService.js
4. backend/services/schedulerService.js
5. backend/services/leadService.js
6. backend/services/resendService.js
7. backend/services/cities.js
8. backend/services/cityRotationService.js
9. outreach-os/server.js

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

New cities now auto-activate via cityRotationService when Stockholm/Gothenburg exhaust.
No need to manually flip `active: true` in cities.js anymore.
