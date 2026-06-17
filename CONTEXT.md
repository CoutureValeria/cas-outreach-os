# CAS Email Engine — System Context

## Deployed services

- Email engine backend: https://cas-email-engine-backend-production-3b02.up.railway.app
- Outreach OS: https://cas-outreach-os-production.up.railway.app
- Dashboard: dashboard/index.html (open locally)
- Database: Supabase — https://tjpkmonazlqmbaazcker.supabase.co
- Email sending: Resend from kasper@casautomations.com (domain verified, eu-west-1)
- Reply detection: Gmail IMAP kaplelbackman@gmail.com (+ second inbox when configured)
- Lead sourcing: vet-intel GitHub Actions daily 08:00 Stockholm

## Current status as of 2026-06-17

### System health
- Send cycle live: 9 vet leads + 6 indeed leads approved and ready
- vet send lane: 09:00/10:00/11:00 Stockholm, type='veterinary'
- indeed lane: 13:00/14:00 Stockholm, type='job-posting' — 6 leads approved with emails
- IMAP live, circuit ok, vet-intel import running daily
- Railway deploy: backend `31b0056`, outreach-os `8a43171` (rebuilt 2026-06-17 — LinkedIn WORKING)
- LinkedIn /api/linkedin/find: WORKING — returns lead object with Swedish connection_note

### Alert emails — reduced to essentials (as of 2026-06-17)
- Health alerts: warm lead notifications only (reply detected → Kasper gets email)
- Weekly summary: every Sunday 18:00 Stockholm — sends pipeline stats + lead counts
- Daily summary emails removed (too noisy)

### indeed-intel pipeline (as of 2026-06-17)
- 15 leads pushed, type fixed to 'job-posting'
- 6 leads enriched and approved (emails found, emails generated, status=approved):
  Lindalens Städ, Svea Bank, R Gruppen Hyr, Avaron, Sugbilar Sverige, Edukatus Alliance
- 7 leads skipped (no email found) + 2 skipped (wrong email from enrichment)
- Pipeline script: `indeed-intel/pipeline_enrich_approve.py` (re-run for any new indeed leads)
- Lane filter: type='job-posting' (source column now being migrated — see below)

### indeed-intel enrichment intelligence (built 2026-06-17)
- **New module:** `indeed-intel/enrichment/` — full structured extraction pipeline
  - `schema.py`    — canonical nested schema: contact{}, decision_maker{}, signals{}
  - `prompt.py`    — strict Swedish SMB extraction prompt (no hallucination, null if missing)
  - `extractor.py` — claude-haiku-4-5-20251001, temp=0, 600 tokens
  - `scoring.py`   — 0–100 automation score:
      booking_system +25 | manual_workflows +20 | appointment_heavy +25
      recruitment_active +10 | no_phone_and_email +10 | opportunities +20
  - `pipeline.py`  — orchestrates extractor + scorer → {data, automation_score, source_url, extraction_success}
- **OpenClaw bridge:** `indeed-intel/collectors/openclaw_client.py`
  - Primary: POSTs to `http://localhost:8888/api/session/webchat/invoke` (30s timeout, 1 retry)
  - Fallback: requests + BeautifulSoup crawl (homepage + 8 subpages) — CURRENTLY ACTIVE
  - OpenClaw Hostinger URL not yet configured → bs4 fallback handling all fetches
  - `get_page_text(url)` is the public API
- **main.py integration:** Phase 2.5 enriches all SEND leads after task scoring, before push
  - Enrichment data merged into research_notes in webhook payload
  - decision_maker.name set as contact_name for email greeting
- **Deleted:** `enrichment/openclaw_enrich.py` (replaced by new module)
- **Test:** `python test_enrichment_pipeline.py` — tested Smartchain (score 40, dm=Jens), Lindalens (score 100), Nord Armering (score 50)

### source column status — needs 1 manual step (optional)
- SUPABASE_SERVICE_ROLE_KEY is now in Railway (added 2026-06-16)
- migrationService.js can't reach Supabase pooler from Railway (tenant not found error)
- emailService.js uses type field as proxy — sends work correctly without source column
- TO ADD SOURCE COLUMN: paste into Supabase SQL editor (dashboard.supabase.com → SQL editor):
  ```sql
  ALTER TABLE leads ADD COLUMN IF NOT EXISTS source text;
  ALTER TABLE sent_log ADD COLUMN IF NOT EXISTS source text;
  ```
  Then run: POST /api/admin/patch-indeed-type (already done — sets type='job-posting' for indeed leads)
  Source column is optional — system works correctly using type field instead

### DB constraints — FIXED 2026-06-15
- leads_status_check now includes all statuses: sending, bounced, out_of_office, sequence_complete
- sent_log_type_check now includes: followup_1, followup_2
- Send lock uses in-process mutex (ff469e2) — simpler than DB status, correct for 1 replica

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
- LinkedIn: WORKING as of 2026-06-17 — outreach-os rebuilt from commit 8a43171
  Endpoint: POST /api/linkedin/find — returns {lead: {..., connection_note, status}}
  Fix used: serviceInstanceDeploy(serviceId, environmentId, latestCommit:true) via Railway GraphQL

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
- Anthropic claude-opus-4-8 for research + email generation (web_search tool)
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
- Weekly summary: Sunday 18:00 Stockholm (pipeline stats + lead counts)
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
