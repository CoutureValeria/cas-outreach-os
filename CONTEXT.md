# CAS Email Engine — System Context

## Deployed services

- Email engine backend: https://cas-email-engine-backend-production-3b02.up.railway.app
- Outreach OS: https://cas-outreach-os-production.up.railway.app
- Dashboard: dashboard/index.html (open locally)
- Database: Supabase — https://tjpkmonazlqmbaazcker.supabase.co
- Email sending: Resend from kasper@casautomations.com (domain verified, eu-west-1)
- Reply detection: Gmail IMAP kaplelbackman@gmail.com (+ second inbox when configured)
- Lead sourcing: vet-intel GitHub Actions daily 08:00 Stockholm

## Current status as of 2026-06-18

### System health
- Send cycle live: 4 indeed leads approved and ready (Avaron, Svea Bank, R Gruppen Hyr, Lindalens)
- vet send lane: 09:00/10:00/11:00 Stockholm, type='veterinary'
- indeed lane: 13:00/14:00 Stockholm, type='job-posting'
- IMAP live, circuit ok, vet-intel import running daily
- Railway deploy: backend `60d4794`, outreach-os `eeb27fb`
- Email tone overhaul (2026-06-18): sign-off = Kasper only, never "vi" always "jag", no company names, no formal opt-out, no em dashes
- LinkedIn /api/linkedin/find: WORKING — returns lead object with Swedish connection_note

### 5-root-cause email volume fix (2026-06-18) — commits aec7679, ca88fee, 7c85c69
Diagnosed why only ~40 emails sent over several weeks. Root causes and fixes:

**CAUSE 1 — Double-send race condition (Railway rolling deploy):**
- Old: in-memory `_sendInProgressVet` flag — two simultaneous instances both read `false`, both send.
- Fix: atomic DB claim in `_doSend()`: `UPDATE leads SET status='sending' WHERE id=? AND status='approved' RETURNING id`.
  If 0 rows returned → another instance won, this instance skips. Postgres serialises concurrent UPDATEs.
- Status: working — AlexVet sent at 18:04 created exactly 1 row. Pre-fix morning sends (sodervet, plutovets) had 2 rows each.

**CAUSE 2 — Deploy during send window kills rest of day:**
- Old: single catch-up send 2h after any missed window.
- Fix: `detectMissedSendWindows()` counts all passed windows today per lane. Queues up to 3 vet + 2 indeed sends with 5-min gaps at startup, all using `force=true`.

**CAUSE 3 — Clearout filtering 43% of valid leads:**
- Old: blocked on `safe_to_send=false` which includes `catch_all` — Swedish SMBs commonly use catch-all.
- Fix: only block when `status === 'invalid'` (hard bounce risk). `catch_all` proceeds with log line.
- Also added chain clinic blocklist (`evidensia`, `anicura`, `djursjukhuset`, `vetgroup`) in `_doSend()` pre-Clearout.

**CAUSE 4 — Indeed pipeline never ran on cron:**
- Old: 08:00 cron only ran vet research. Indeed leads stayed `status='new'` forever unless manually triggered.
- Fix: `runVetIntelPipeline()` now has explicit indeed block — processes up to 5 `type='job-posting'` leads per day.

**CAUSE 5 — Daily limits too low:**
- Old: VET_DAILY_LIMIT=3, INDEED_DAILY_LIMIT=1.
- Fix: VET_DAILY_LIMIT=5, INDEED_DAILY_LIMIT=3 (env fallback in emailService.js).

**force=true behaviour (ca88fee):**
- Now bypasses: business hours check, circuit breaker, AND hourly gap.
- Only bypassed before: business hours + circuit breaker. Hourly gap was blocking recovery sends.

**New endpoint (7c85c69):**
- `POST /api/send/next-indeed` — manual force-send for indeed lane (mirrors `/api/send/next`)

**CAUSE 6 — Lane count query bug (2f3c185):**
- `getTodaySentCountForLane()` used PostgREST `.eq('leads.type', x)` filter in `head:true` count mode.
- PostgREST ignores embedded table filters in count/head mode — both lanes always returned TOTAL sent count.
- Effect: any day with ≥3 total vet sends showed indeed as "limit reached" (0 indeed actually sent).
- Fix: fetch all today's sent_log rows with lead type, filter in JS: `data.filter(r => r.leads?.type === leadType).length`

**Verification (2026-06-18 sent_log):**
- sodervet × 2, plutovets × 2 — double-sends from PRE-FIX morning crons (old code was live)
- alexvet × 1 (18:04 UTC), svea.com × 1 (18:17 UTC), avaron.se × 1 (18:17 UTC) — all POST-FIX, each exactly 1 row

**Capacity at full operation:**
- Vet: 3 cron slots/day (09/10/11) × 5 days = 15/week typical; VET_DAILY_LIMIT=5 allows startup recovery to send up to 5/day
- Indeed: 2 cron slots/day (13/14) × 5 days = 10/week typical; INDEED_DAILY_LIMIT=3 allows 1 extra via startup recovery
- Total: ~25/week (up from ~7/week actual before fixes)

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

### indeed-intel enrichment intelligence (updated 2026-06-18)
- **Module:** `indeed-intel/enrichment/` — full structured extraction pipeline
  - `schema.py`    — canonical nested schema: contact{}, decision_maker{}, signals{}
  - `prompt.py`    — strict Swedish SMB extraction prompt (no hallucination, null if missing)
  - `extractor.py` — claude-haiku-4-5-20251001, temp=0, 600 tokens
  - `scoring.py`   — 0–100 automation score (FIXED 2026-06-18):
      booking_system present → -10 (already solved, no pain)
      booking_system absent + appointment_heavy → +35 (high pain)
      booking_system absent + NOT appointment_heavy → +15 (generic manual pain)
      manual_workflows +20 | recruitment_active +10 | no_phone_and_email +10 | opportunities +20
  - `pipeline.py`  — orchestrates extractor + scorer → {data, automation_score, source_url, extraction_success}
- **OpenClaw bridge:** `indeed-intel/collectors/openclaw_client.py` (updated 2026-06-18)
  - Reads `OPENCLAW_URL` from env var (not hardcoded localhost)
  - Set `OPENCLAW_URL=https://your-hostinger/api/session/webchat/invoke` in `indeed-intel/.env`
  - `get_page_text(url)` — raw text path (OpenClaw generic prompt → bs4 fallback)
  - `get_company_json(url)` — NEW: CAS-specific research prompt, returns structured JSON directly
      Uses `_OPENCLAW_CAS_PROMPT` — full CAS lead researcher persona, visits 4 page types,
      returns JSON with phone/email/booking_system/decision_maker/automation_opportunities
      Falls back to None → callers use get_page_text + Claude Haiku as fallback
  - Currently: OPENCLAW_URL not set → bs4 fallback active for all fetches
- **Gothenburg added** (2026-06-18): `indeed-intel/config/settings.py`
  - `MUNICIPALITY_GOTHENBURG = "1480"` + `GOTHENBURG_QUERIES` (7 query types)
  - `CITY_SEARCH_CONFIGS` list — Stockholm + Gothenburg both active
  - `platsbanken.py` `fetch_postings()` now iterates all city configs
  - Test fetch: 29 Gothenburg postings passed filters (18 agency, 1 gov, 1 enterprise filtered)
  - `fetch_postings(cities=['Gothenburg'])` to fetch single city
- **main.py integration:** Phase 2.5 enriches all SEND leads after task scoring, before push
  - Enrichment data merged into research_notes in webhook payload
  - decision_maker.name set as contact_name for email greeting
- **Test scores** (after scoring fix 2026-06-18):
  - Smartchain: 55 (was 40) | Lindalens: 40 (was 100) | Nord Armering: 65 (was 50)

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
- Send lock: in-process mutex REPLACED (2026-06-18) with atomic DB claim — UPDATE WHERE status='approved' RETURNING id

### Email sequence (3-touch)
- **Initial (day 0):** DISCOVERY style — asks an open question about their operational pain. No solution pitch. (Changed 2026-06-14)
- **Follow-up (day 5):** Solution-oriented, references research_notes pain signal, "Fortfarande värt en titt?"
  - Vet leads: clinic-specific, references missed bookings / clients going elsewhere
  - Indeed leads (type=job-posting): references job posting angle, hiring for manual work, cost of hiring vs automating
- **Breakup (day 10):** "Jag förstår om timing inte är rätt just nu." + closing line
  - Vet leads: choice of 2 lines (months? or specific issue?)
  - Indeed leads (type=job-posting): exact line "Vill du att jag hör av mig igen om 2-3 månader, eller passar det bättre att ni löser det internt först?"
- After breakup: status = `sequence_complete`, re_engage_after = now+90d
- `sendDueFollowUps()` and `sendDueFollowUp2s()` pick up ALL sent leads (vet + indeed), route by `lead.type`
- PGRST205 fallback active (migrationService.js adds columns at startup via Supabase pooler probe)
- /api/test/status shows `sequence_complete` count + `breakup_sent_7d`

### Sign-off (all 3 emails)
`Kasper` — just the first name, no company, no title. Applies to initial + FU1 + breakup for both vet and indeed leads.

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
  - Examples: "Vad tar mest tid av det administrativa just nu, samtal, bokningar, eller uppföljning?"
  - No product. No "Vi löser det". No CTA beyond the question itself.
- Opt-out line (exact, before sign-off): `Hör inte av dig om det inte känns relevant, ingen stress.`
- Sign-off: `Kasper` (no company, no title)
- LANGUAGE RULES (all email types): Never use "vi" — always "jag". Never mention Drivverk AB, CAS Automations, or any company name. Must sound like a curious individual, not a company doing outreach.

### Follow-up (solution pitch, day 5)
- 2 lines before sign-off
- Reframes around what they are LOSING (missed bookings, clients going elsewhere)
- Ends with: "Fortfarande värt en titt?"
- NO opt-out line — just the question and sign-off: `Kasper`
- Generated per-lead using claude-haiku-4-5-20251001, references research_notes pain signal

### Breakup (final, day 10)
- 2 lines before sign-off
- Line 1 (exact): "Jag förstår om timing inte är rätt just nu."
- Line 2 (exact): "Hör gärna av dig om det någonsin blir aktuellt, annars hör jag inte av mig mer."
- Sign-off: `Kasper` (no opt-out line, Line 2 doubles as natural close)

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

- Mon–Fri vet: 09:00, 10:00, 11:00 Stockholm — VET_DAILY_LIMIT=5
- Mon–Fri indeed: 13:00, 14:00 Stockholm — INDEED_DAILY_LIMIT=3
- Daily pipeline: 08:00 Mon-Fri Stockholm (research + generate for vet AND indeed new leads)
- Health check: every 6h UTC
- Weekly summary: Sunday 18:00 Stockholm (pipeline stats + lead counts)
- IMAP poll: every 30 minutes (all configured inboxes in parallel)
- Manual sends: POST /api/send/next (vet), POST /api/send/next-indeed (indeed) — both accept {force:true}

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
