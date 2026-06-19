# CAS Email Engine — System Context

## Deployed services

- Email engine backend: https://cas-email-engine-backend-production-3b02.up.railway.app
- Outreach OS: https://cas-outreach-os-production.up.railway.app
- Dashboard: dashboard/index.html (open locally)
- Database: Supabase — https://tjpkmonazlqmbaazcker.supabase.co
- Email sending: Resend from kasper@casautomations.com (domain verified, eu-west-1)
- Reply detection: Gmail IMAP kaplelbackman@gmail.com
- Lead sourcing: vet-intel GitHub Actions daily 08:00 Stockholm

## Resend delivery note

Emails are sent via Resend API, NOT via Gmail/Zoho SMTP. Sent emails do NOT appear
in any Gmail or Zoho Sent folder — this is expected behaviour. Resend dashboard is the
source of truth for delivery status, opens, and bounces.

## Current status as of 2026-06-19

### System health
- Full system operational end-to-end
- Backend latest commit: `60d4794` (email tone overhaul)
- Outreach-OS latest commit: `8072170` (OpenClaw removed, bs4 is permanent)
- Vet lane: 09:00/10:00/11:00 Stockholm, type='veterinary', VET_DAILY_LIMIT=5
- Indeed lane: 13:00/14:00 Stockholm, type='job-posting', INDEED_DAILY_LIMIT=3
- IMAP live, circuit ok, vet-intel import running daily
- LinkedIn /api/linkedin/find: WORKING

---

## Email volume fixes (2026-06-18) — 6 root causes resolved

### CAUSE 1 — Double-send race condition (Railway rolling deploy)
- **Old:** in-memory `_sendInProgressVet` flag — two simultaneous instances both read `false`, both send
- **Fix:** atomic DB claim in `_doSend()`: `UPDATE leads SET status='sending' WHERE id=? AND status='approved' RETURNING id`
  If 0 rows returned → another instance already claimed it, this instance skips. Postgres serialises concurrent UPDATEs.

### CAUSE 2 — Deploy during send window kills rest of day
- **Old:** single catch-up send 2h after any missed window
- **Fix:** `detectMissedSendWindows()` counts ALL passed windows today per lane. On boot, queues up to 3 vet + 2 indeed sends with 5-min gaps, all using `force=true`

### CAUSE 3 — Clearout filtering 43% of valid leads
- **Old:** blocked on `safe_to_send=false` which includes `catch_all` — Swedish SMBs routinely use catch-all
- **Fix:** only block when Clearout returns `status === 'invalid'`. `catch_all` proceeds with a log line.
- Chain clinic blocklist (`evidensia`, `anicura`, `djursjukhuset`, `vetgroup`) enforced in `_doSend()` BEFORE Clearout check

### CAUSE 4 — Indeed pipeline never ran on cron
- **Old:** 08:00 cron only ran vet research. Indeed leads stayed `status='new'` forever
- **Fix:** `runVetIntelPipeline()` now has an explicit indeed block — processes up to 5 `type='job-posting'` leads per day

### CAUSE 5 — Daily limits too low
- **Old:** VET_DAILY_LIMIT=3, INDEED_DAILY_LIMIT=1
- **Fix:** VET_DAILY_LIMIT=5, INDEED_DAILY_LIMIT=3 (env vars in Railway, fallback in emailService.js)

### CAUSE 6 — Lane count query bug
- `getTodaySentCountForLane()` used PostgREST `.eq('leads.type', x)` in `head:true` count mode
- PostgREST ignores embedded table filters in count/head mode — both lanes returned TOTAL sent count
- **Fix:** fetch all today's sent_log rows with lead type, filter in JS: `data.filter(r => r.leads?.type === leadType).length`

**force=true bypasses:** business hours check + circuit breaker + hourly gap

**New endpoint:** `POST /api/send/next-indeed` — manual force-send for indeed lane

**Capacity at full operation:**
- Vet: 3 slots/day × 5 days = ~15/week; VET_DAILY_LIMIT=5 allows startup recovery
- Indeed: 2 slots/day × 5 days = ~10/week; INDEED_DAILY_LIMIT=3 allows 1 extra via recovery
- Total: ~25/week (up from ~7/week before fixes)

---

## Email tone overhaul (2026-06-18)

- Sign-off: `Kasper` only — no company name, no title, on all 3 email types for both lanes
- Voice: always `jag`, never `vi`. No company names (not Drivverk AB, not CAS Automations)
- Em dashes: `sanitizeEmail()` strips all `—` and `–` from every generated email (10 output paths covered)
- Opt-out language: natural, varies by type — never formal boilerplate
- Emails must sound like a curious individual, not a company doing outreach

---

## Email sequence (3-touch)

### Initial (day 0) — Discovery
- LINE 1: Hook based on a specific website signal or observation
- LINES 2-3: Open question about which operational area feels heaviest
- Opt-out (exact, before sign-off): `Hör inte av dig om det inte känns relevant, ingen stress.`
- Sign-off: `Kasper`

### Follow-up (day 5) — Solution pitch
- 2 lines, reframes around what they are LOSING
- Ends with: `Fortfarande värt en titt?`
- No opt-out line — just the question and `Kasper`
- Vet leads: references missed bookings / clients going elsewhere
- Indeed leads (job-posting): references job posting, cost of hiring vs automating

### Breakup (day 10) — Final
- Line 1 (exact): `Jag förstår om timing inte är rätt just nu.`
- Line 2 (exact): `Hör gärna av dig om det någonsin blir aktuellt, annars hör jag inte av mig mer.`
- Sign-off: `Kasper`

### After breakup
- status = `sequence_complete`, re_engage_after = now+90d
- `sendDueFollowUps()` and `sendDueFollowUp2s()` pick up ALL sent leads (vet + indeed), route by `lead.type`

---

## indeed-intel pipeline

### Enrichment stack (permanent)
- **Crawler:** `indeed-intel/collectors/openclaw_client.py` — `get_page_text(url)`
  - BeautifulSoup4 + requests, crawls homepage + up to 8 subpages (om-oss, kontakt, team, etc.)
  - Swedish User-Agent, 0.25s polite delay between subpages
  - Returns concatenated text; None if site unreachable
  - OpenClaw evaluated 2026-06-19 and deprioritized — bs4 + Claude Haiku is permanent
- **Extraction:** `indeed-intel/enrichment/extractor.py` — claude-haiku-4-5-20251001, temp=0, 600 tokens
- **Schema:** `indeed-intel/enrichment/schema.py` — nested: contact{}, decision_maker{}, signals{}
- **Prompt:** `indeed-intel/enrichment/prompt.py` — strict Swedish SMB extraction, null if uncertain
- **Scoring:** `indeed-intel/enrichment/scoring.py` — 0-100 automation score:
  - booking_system present → -10 (already solved, no pain)
  - booking_system absent + appointment_heavy → +35 (high pain)
  - booking_system absent + NOT appointment_heavy → +15 (generic manual pain)
  - manual_workflows +20 | recruitment_active +10 | no_phone_and_email +10 | opportunities +20
- **Pipeline:** `indeed-intel/enrichment/pipeline.py` — orchestrates → `{data, automation_score, source_url, extraction_success}`

### City coverage
- Stockholm (municipality 0180) + Gothenburg (municipality 1480) both active
- `CITY_SEARCH_CONFIGS` in `indeed-intel/config/settings.py` — add more cities here
- 7 Gothenburg query types: receptionist, kundtjänst, bokningsansvarig, administratör, koordinator, orderhantering, innesäljare
- Run: `python pipeline_enrich_approve.py` to enrich new leads
- `fetch_postings(cities=['Gothenburg'])` to test single city

### Pipeline results (2026-06-17/18)
- 95 postings fetched (Stockholm + Gothenburg combined)
- 19 new leads pushed to Supabase as type='job-posting'
- 1 approved after enrich (Committo AB → rebecca.oldenfeldt@committo.se)
- Email find rate: ~22/24 had no findable email via bs4 — expected, most use ATS/job boards

---

## Alert emails (reduced 2026-06-17)
- Warm lead alert: immediate email to Kasper when a reply is detected
- Weekly summary: every Sunday 18:00 Stockholm — pipeline stats + lead counts
- Daily summaries removed (too noisy)

---

## City rotation framework (live 2026-06-14)

- **20 Swedish cities** in cities.js (Stockholm → Sundsvall by population)
- **Active:** Stockholm + Gothenburg; 18 others queued inactive
- vet-intel calls `GET /api/cities/next` at start of each run
- vet-intel calls `POST /api/cities/complete-run` with `{city, leads_found}` after push
- **Exhaustion rule:** 3 consecutive zero-lead runs → city marked exhausted
- When ALL active cities exhausted → next inactive city auto-activates
- State: `system_state` Supabase table, key `city_rotation_state`
- Endpoints: `GET /api/cities/next`, `POST /api/cities/complete-run`, `GET /api/cities/status`

**City order:** Stockholm → Gothenburg → Malmö → Uppsala → Linköping → Örebro → Västerås → Helsingborg → Norrköping → Jönköping → Lund → Umeå → Gävle → Borås → Eskilstuna → Södertälje → Karlstad → Växjö → Halmstad → Sundsvall

New cities use Stockholm credentials (kasper@casautomations.com) until a second domain/Gmail is configured.

---

## vet-intel SEND filter
- Score threshold ≥ 45 (was ≥ 60)
- Medium-signal leads included
- QUEUE bucket eliminated — all leads go to SEND or IGNORE
- API-driven city rotation (as of 2026-06-14)

---

## Social outreach
- Instagram: 6 leads in DB (dm_sent), endpoint working
- LinkedIn: WORKING — `POST /api/linkedin/find` returns `{lead: {..., connection_note, status}}`

---

## DB constraints
- leads_status_check: new, approved, sending, sent, bounced, out_of_office, sequence_complete
- sent_log_type_check: initial, followup_1, followup_2
- Send lock: atomic DB claim (`UPDATE WHERE status='approved' RETURNING id`) — no in-process mutex

## Schema notes
- leads table has NO pain-specific columns (primary_pain, pain_evidence, etc. do NOT exist)
- All pain data lives in `research_notes` JSON blob
- `follow_up_2_sent_at` and `re_engage_after` (timestamptz) added by migrationService.js at startup
- PGRST205 fallback active — code works before migration columns land

## source column (optional, not built)
- System uses `type` field as proxy for vet vs indeed routing — works correctly without source column
- To add: `ALTER TABLE leads ADD COLUMN IF NOT EXISTS source text;` in Supabase SQL editor

---

## Architecture

- Node.js/Express on Railway (backend + outreach-os as separate services)
- Supabase (Postgres) via PostgREST + service_role JWT
- claude-opus-4-8 for research + initial email generation (web_search tool)
- claude-haiku-4-5-20251001 for follow-up/breakup generation and indeed enrichment extraction
- Resend for delivery (kasper@casautomations.com, eu-west-1)
- node-cron with Europe/Stockholm timezone
- Clearout for email verification (CLEAROUT_API_KEY in Railway)

## Send schedule
- Mon-Fri vet: 09:00, 10:00, 11:00 Stockholm
- Mon-Fri indeed: 13:00, 14:00 Stockholm
- Daily pipeline: 08:00 Mon-Fri Stockholm (vet + indeed new leads)
- Health check: every 6h UTC
- Weekly summary: Sunday 18:00 Stockholm
- IMAP poll: every 30 min
- Manual: `POST /api/send/next` (vet), `POST /api/send/next-indeed` (indeed) — both accept `{force:true}`

## Key env vars (Railway — backend)

RESEND_API_KEY, ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_ANON_KEY,
SUPABASE_SERVICE_ROLE_KEY, BACKEND_API_KEY, GMAIL_ADDRESS, GMAIL_APP_PASSWORD,
REPLY_TO=cas@casautomations.com, USE_VETINTEL_ONLY=true,
GITHUB_TOKEN, CLEAROUT_API_KEY,
VET_DAILY_LIMIT=5, INDEED_DAILY_LIMIT=3

---

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

---

## Multi-city second domain setup (when ready)

1. Register casautomations.se at Loopia/Namecheap
2. Create second Gmail + App Password (16 chars)
3. Set in Railway: SECOND_GMAIL_ADDRESS, SECOND_GMAIL_APP_PASSWORD, SECOND_DOMAIN_FROM, SECOND_DOMAIN_REPLY_TO
4. Tell Claude — will add domain to Resend via API and verify DNS

New cities auto-activate via cityRotationService — no manual `active: true` flip needed.
