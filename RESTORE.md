I am continuing work on the CAS Automations outreach system.

Read these files in order before doing anything:
1. backend/CONTEXT.md — full system overview, current status, Outreach OS details
2. backend/services/emailService.js — email sending and scheduling
3. backend/services/gmailPoller.js — IMAP reply detection (two-pass fetch fix)
4. backend/server.js — API routes and webhook handlers
5. outreach-os/server.js — Outreach OS API routes
6. dashboard/index.html — unified frontend

System is deployed on:
- Email engine backend: Railway — https://cas-email-engine-backend-production-3b02.up.railway.app
- Email engine frontend: Railway (static HTML) — https://cas-email-engine-frontend.vercel.app/
- Outreach OS: NOT YET DEPLOYED — repo ready at CoutureValeria/cas-outreach-os, awaiting Railway setup
- Unified dashboard: /dashboard/index.html — open locally or deploy to Vercel/Railway
- Lead sourcing: vet-intel on GitHub Actions (daily 08:00 Stockholm)
- Database: Supabase — https://tjpkmonazlqmbaazcker.supabase.co
- Email sending: Resend (primary), Gmail SMTP fallback
- Reply detection: Gmail IMAP kaplelbackman@gmail.com (polling every 30 min)

Current status as of 2026-06-08:
- Email engine fully operational — pipeline running end to end
- IMAP two-pass fetch fix deployed — reply detection working
- Outreach OS service built (/outreach-os) — needs Railway deployment
- Unified dashboard built (/dashboard/index.html) — connects to both backends
- linkedin_leads Supabase table NOT YET CREATED — run schema SQL first

One-time task before using Outreach OS:
  Run outreach-os/database/schema.sql in Supabase SQL editor:
  https://supabase.com/dashboard/project/tjpkmonazlqmbaazcker/sql

Deploy Outreach OS to Railway:
  1. New Service → GitHub Repo → CoutureValeria/cas-outreach-os → Root Directory: outreach-os
  2. Set env vars: OUTREACH_OS_API_KEY, ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_ANON_KEY
  3. After deploy: open dashboard/index.html Settings and fill in the new Railway URL

Known issues / next:
- Outreach OS not yet deployed to Railway (awaiting manual Railway UI step)
- linkedin_leads table not yet created in Supabase (awaiting manual SQL run)
- GOOGLE_SERVICE_ACCOUNT_JSON not set (Google Sheets sync inactive — optional)
- Facebook Messenger channel not active (no FB env vars — optional)

Do not make any changes until you have read all files listed above.
Then tell me the current state and ask what to work on.
