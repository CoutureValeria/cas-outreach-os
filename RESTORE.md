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
- Email sending: Resend from kasper@casautomations.com (NOT Gmail/Zoho — sent items won't appear there)
- Reply detection: Gmail IMAP kaplelbackman@gmail.com
- Lead sourcing: vet-intel GitHub Actions daily 08:00 Stockholm

Current status as of 2026-06-19:
- Full system operational — 6 email volume root causes fixed, tone overhaul deployed
- OpenClaw evaluated and removed — bs4 + Claude Haiku is the permanent enrichment stack
- Backup: email-engine-backup-2026-06-19.zip on Desktop (includes vet-intel)
- All repos clean and pushed

Next-session priorities:

1. MONITOR REPLY RATE — WAIT 1-2 WEEKS BEFORE ACTING
   - Watch warm_lead_reply content in Supabase for both vet and indeed lanes
   - Key question: are replies describing real operational pain, or just opt-outs?
   - If replies describe real problems → enrichment quality and email copy are working
   - If mostly opt-outs → consider improving hook specificity or enrichment depth
   - DO NOT change email strategy until at least 1-2 weeks of reply data is in

2. CHECK GOTHENBURG INDEED-INTEL LEAD QUALITY
   - Run pipeline_enrich_approve.py after a fresh fetch of Gothenburg postings
   - Compare email-find rate and automation scores vs Stockholm batch
   - Gothenburg queries: receptionist, kundtjänst, bokningsansvarig, administratör, koordinator, orderhantering, innesäljare

3. CONSIDER BCC-TO-SELF ON RESEND SENDS (optional)
   - Resend does not put emails in Gmail Sent folder (expected behaviour)
   - If Kasper wants a visible copy in his own inbox: add BCC to resendService.js send calls
   - Low effort, ask Kasper if he wants it before building

4. MONITOR CITY EXHAUSTION
   - Check GET /api/cities/status periodically
   - When Stockholm or Gothenburg hits consecutive_zeros = 3 → auto-exhausted
   - When both exhausted → Malmö should auto-activate (verify it does)
   - CITY_OVERRIDE env var in vet-intel GitHub Secrets for manual city override

5. SOURCE COLUMN (optional, low priority)
   - System works correctly without it (uses type field as proxy)
   - To add: paste in Supabase SQL editor:
     ALTER TABLE leads ADD COLUMN IF NOT EXISTS source text;
     ALTER TABLE sent_log ADD COLUMN IF NOT EXISTS source text;

6. INDUSTRY EXPANSION — NOT YET
   - Real estate agents and mechanics are the planned second industry
   - Do NOT start until 1-2 weeks of reply data is reviewed (see #1)

7. SECOND DOMAIN FOR GOTHENBURG (when ready)
   - Register casautomations.se at Loopia/Namecheap
   - Create second Gmail + App Password
   - Set SECOND_DOMAIN_FROM, SECOND_GMAIL_ADDRESS etc. in Railway
   - Tell Claude to add the domain to Resend via API
   - Gothenburg currently sends via Stockholm domain (fallback, works fine)

Do not make changes until you have read all files above.
Tell me current state then ask what to work on.
