Read CONTEXT.md and these files before doing anything:
1. CONTEXT.md
2. backend/services/emailService.js
3. backend/services/healthAlertService.js
4. backend/services/schedulerService.js
5. backend/services/cities.js
6. backend/services/cityRotationService.js
7. outreach-os/server.js
8. dashboard/index.html

System deployed on:
- Email engine: Railway — https://cas-email-engine-backend-production-3b02.up.railway.app
- Outreach OS: https://cas-outreach-os-production.up.railway.app
- Dashboard: dashboard/index.html (open locally)
- Database: Supabase — https://tjpkmonazlqmbaazcker.supabase.co
- Email sending: Resend from kasper@casautomations.com
- Reply detection: Gmail IMAP kaplelbackman@gmail.com
- Lead sourcing: vet-intel GitHub Actions daily 08:00 Stockholm

Current status as of 2026-06-18:
- Full system operational end to end — email volume fix + email tone overhaul deployed
- Backend at commit 60d4794 — tone/opt-out/em-dash fixes live
- Outreach-OS at commit eeb27fb — indeed prompts + CONTEXT.md em-dash fixes live
- Vet lane: ~15 sends/week (3 cron slots × 5 days). Indeed lane: ~10 sends/week (2 slots × 5 days)
- 20-city rotation framework live (Stockholm + Gothenburg active, 18 queued)
- Discovery-style initial emails live (questions, not pitches)
- indeed-intel enrichment intelligence module live + scoring fixed
- OpenClaw bridge: reads OPENCLAW_URL from env — set it in indeed-intel/.env when ready
- indeed-intel now covers Stockholm + Gothenburg (CITY_SEARCH_CONFIGS)
- Follow-up + breakup sequence now covers both vet AND indeed leads (job-posting type)
- LinkedIn working after Railway rebuild (commit 8a43171)
- Alert emails: warm lead notification only + weekly Sunday summary

Next-session priorities:

1. SET OPENCLAW_URL
   - Set OPENCLAW_URL=https://your-hostinger-url/api/session/webchat/invoke in indeed-intel/.env
   - Two paths now available: get_page_text() (raw text + Claude Haiku) and get_company_json() (CAS prompt → JSON)
   - After setting: run python test_enrichment_pipeline.py to confirm OpenClaw takes over from bs4

3. MONITOR FIRST WEEK OF INDEED-INTEL SENDS FOR REPLY DATA
   - 6 indeed leads are now approved and in the send queue (13:00/14:00 slot)
   - Watch for: reply rate, opt-outs, warm_lead_reply content
   - Compare quality vs vet-intel leads (which have more research depth)
   - If indeed leads produce replies describing real problems → enrichment quality is good
   - If mostly opt-outs → consider improving email copy or enrichment depth

4. WATCH REPLY RATE ON VET-INTEL DISCOVERY EMAILS (1-2 weeks before acting)
   - Give the discovery emails 1-2 weeks to collect data before deciding anything
   - Key question: do replies contain described problems or just opt-outs?
   - If reply rate improves → keep discovery style
   - If reply rate is flat/worse vs old pitch style → consider A/B or reverting
   - Check warm_lead_reply content in the DB to see what people are saying
   - DO NOT build industry expansion until this data is in

5. SOURCE COLUMN (optional, low priority)
   - Run this SQL in Supabase dashboard if you want source tracking:
     ALTER TABLE leads ADD COLUMN IF NOT EXISTS source text;
     ALTER TABLE sent_log ADD COLUMN IF NOT EXISTS source text;
   - System works correctly without it (uses type field as proxy)

6. MONITOR CITY EXHAUSTION (Stockholm/Gothenburg)
   - Check GET /api/cities/status periodically
   - When Stockholm or Gothenburg hits consecutive_zeros = 3 → auto-exhausted
   - When both exhausted → Malmö should auto-activate (check it does)
   - CITY_OVERRIDE env var in vet-intel GitHub Secrets bypasses rotation for manual testing

7. INDUSTRY EXPANSION — NEXT PHASE, NOT YET BUILT
   - Real estate agents and mechanics are the planned second industry
   - Do NOT start until discovery email reply data is reviewed (see #4)

8. SECOND DOMAIN FOR GOTHENBURG (when ready)
   - Register casautomations.se at Loopia/Namecheap
   - Create second Gmail + App Password
   - Set SECOND_DOMAIN_FROM, SECOND_GMAIL_ADDRESS etc. in Railway
   - Tell Claude to add the domain to Resend via API
   - Gothenburg currently sends via Stockholm domain (fallback, works fine)

Do not make changes until you have read all files above.
Tell me current state then ask what to work on.
