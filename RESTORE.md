I am continuing work on the CAS Automations outreach system.

Read these files in order before doing anything:
1. backend/CONTEXT.md — full system overview, current status, all fixes deployed
2. backend/services/schedulerService.js — cron schedule + startup recovery logic
3. backend/services/emailService.js — send rules, in-memory lock, circuit breaker
4. backend/services/stateService.js — persistent state service (Supabase + in-memory fallback)
5. backend/server.js — API routes, migration endpoint

System is deployed on:
- Email engine backend: Railway — https://cas-email-engine-backend-production-3b02.up.railway.app
- Email engine frontend: Railway (static HTML) — https://cas-email-engine-frontend.vercel.app/
- Outreach OS: NOT YET DEPLOYED — repo ready at CoutureValeria/cas-outreach-os, awaiting Railway setup
- Unified dashboard: /dashboard/index.html — open locally or deploy to Vercel/Railway
- Lead sourcing: vet-intel on GitHub Actions (daily 08:00 Stockholm)
- Database: Supabase — https://tjpkmonazlqmbaazcker.supabase.co
- Email sending: Resend (primary), Gmail SMTP fallback
- Reply detection: Gmail IMAP kaplelbackman@gmail.com (polling every 30 min)

Current status as of 2026-06-09:
- Email engine fully operational — pipeline running end to end
- IMAP two-pass fetch fix deployed — reply detection working
- Send lock fixed — was broken since the lock was introduced (DB enum constraint rejected 'sending' status)
- Startup recovery deployed — missed send windows auto-recovered 30s after boot
- Persistent state service deployed — stateService.js reads/writes to system_state table (in-memory fallback until migration runs)
- 21 approved leads with emails, 0 null-email leads, 6 sent total
- Last send: info@vetjosefine.se on 2026-06-09 14:06 UTC
- Next scheduled send: Tue 2026-06-10 09:00 Stockholm

API key: 1790f2bc89c3b684ae79d51d73d2e0a550797e34c243dd23383d0df70fda6a58

One-time task — activate persistent state (FIX 2):
  Run database/schema_update.sql in Supabase SQL editor OR call:
  POST /api/admin/run-migration (X-API-Key header required)
  SQL editor: https://supabase.com/dashboard/project/tjpkmonazlqmbaazcker/sql
  This creates the system_state table. Until then, state resets on restart (in-memory fallback active).

One-time task — Outreach OS deploy (still pending):
  1. New Service → GitHub Repo → CoutureValeria/cas-outreach-os → Root Directory: outreach-os
  2. Set env vars: OUTREACH_OS_API_KEY, ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_ANON_KEY
  3. Run outreach-os/database/schema.sql in Supabase SQL editor (linkedin_leads table)

Do not make any changes until you have read all files listed above.
Then tell me the current state and ask what to work on.
