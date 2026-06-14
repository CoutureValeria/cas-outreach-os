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

Current status as of 2026-06-14:
- Full system operational end to end
- 20-city rotation framework live (Stockholm + Gothenburg active, 18 queued)
- Discovery-style initial emails live (questions, not pitches)
- Follow-up (day 5) and breakup (day 10) remain solution-oriented
- vet-intel: API-driven city rotation, reports complete-run to engine after each run
- Clearout email verification active
- SEND filter: score ≥ 45, medium signals included, QUEUE bucket eliminated

Next-session priorities:

1. WATCH REPLY RATE ON DISCOVERY EMAILS (1-2 weeks before acting)
   - Give the discovery emails 1-2 weeks to collect data before deciding anything
   - Key question: do replies contain described problems or just opt-outs?
   - If reply rate improves → keep discovery style
   - If reply rate is flat/worse vs old pitch style → consider A/B or reverting
   - Check warm_lead_reply content in the DB to see what people are saying
   - DO NOT build industry expansion until this data is in

2. MONITOR CITY EXHAUSTION (Stockholm/Gothenburg)
   - Check GET /api/cities/status periodically
   - When Stockholm or Gothenburg hits consecutive_zeros = 3 → auto-exhausted
   - When both exhausted → Malmö should auto-activate (check it does)
   - If auto-activation fails for any reason → cityRotationService.js is the place to debug
   - CITY_OVERRIDE env var in vet-intel GitHub Secrets bypasses rotation for manual testing

3. INDUSTRY EXPANSION — NEXT PHASE, NOT YET BUILT
   - Real estate agents and mechanics are the planned second industry
   - Do NOT start until discovery email reply data is reviewed (see #1)
   - When ready: add industry field to leads table, new email prompts per industry,
     new vet-intel target queries, new scoring profiles

4. SECOND DOMAIN FOR GOTHENBURG (when ready)
   - Register casautomations.se at Loopia/Namecheap
   - Create second Gmail + App Password
   - Set SECOND_DOMAIN_FROM, SECOND_GMAIL_ADDRESS etc. in Railway
   - Tell Claude to add the domain to Resend via API
   - Gothenburg currently sends via Stockholm domain (fallback, works fine)

Do not make changes until you have read all files above.
Tell me current state then ask what to work on.
