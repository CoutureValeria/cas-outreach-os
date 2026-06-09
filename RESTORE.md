Read CONTEXT.md and these files before doing anything:
1. CONTEXT.md
2. backend/services/emailService.js
3. backend/services/healthAlertService.js
4. backend/services/stateService.js
5. outreach-os/server.js
6. dashboard/index.html

System deployed on:
- Email engine: Railway — https://cas-email-engine-backend-production-3b02.up.railway.app
- Outreach OS: https://cas-outreach-os-production.up.railway.app
- Dashboard: dashboard/index.html (open locally)
- Database: Supabase — https://tjpkmonazlqmbaazcker.supabase.co
- Email sending: Resend from kasper@casautomations.com
- Reply detection: Gmail IMAP kaplelbackman@gmail.com
- Lead sourcing: vet-intel GitHub Actions daily 08:00 Stockholm

Current status as of 2026-06-09:
- Full system operational end to end
- 21 approved leads ready to send
- Next send: Tuesday June 10 09:00 Stockholm
- Outreach OS live with Instagram and LinkedIn modules
- Unified dashboard controlling both systems
- linkedin_leads and system_state tables exist in Supabase
- Missed window startup recovery active (30s after boot)
- IMAP reply detection working, health alerts fixed

Known issues to fix next:
- system_state table needs testing after restart
- Outreach OS LinkedIn and Instagram not yet tested with real leads
- Enhanced pain detection improvements still pending

Do not make changes until you have read all files above.
Tell me current state then ask what to work on.
