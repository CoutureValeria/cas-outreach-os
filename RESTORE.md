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

Current status as of 2026-06-17:
- Full system operational end to end
- 20-city rotation framework live (Stockholm + Gothenburg active, 18 queued)
- Discovery-style initial emails live (questions, not pitches)
- indeed-intel enrichment intelligence module built and live
- OpenClaw bridge built — using bs4 fallback (Hostinger URL not yet configured)
- LinkedIn working after Railway rebuild (commit 8a43171)
- Alert emails: warm lead notification only + weekly Sunday summary

Next-session priorities:

1. CONFIGURE OPENCLAW HOSTINGER URL
   - OpenClaw is deployed on Hostinger but URL not yet set in openclaw_client.py
   - File: indeed-intel/collectors/openclaw_client.py, line: _OPENCLAW_URL = "http://localhost:8888/..."
   - Replace localhost:8888 with the real Hostinger URL
   - After setting: test with python test_enrichment_pipeline.py — OpenClaw should take over from bs4
   - If OpenClaw returns richer text than bs4, enrichment quality will improve significantly

2. REVIEW LINDALENS SCORING LOGIC (booking_system signal direction)
   - Lindalens Städ scored 100/100 on automation score — check if that's directionally correct
   - booking_system=True gives +25, but a company ALREADY having a booking system may need LESS automation
   - Consider whether booking_system should signal "we handle lots of bookings" (high automation need)
     vs "we already have it covered" (low automation need)
   - Current logic: booking_system=True → +25 (treats it as "appointment-heavy business")
   - If the signal is misleading for outreach targeting, invert or remove it from the score

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
