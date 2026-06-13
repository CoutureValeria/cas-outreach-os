# CAS Email Engine — Inbox & Domain Warmup Schedule

## Why warmup matters

New sending domains and Gmail accounts start with zero reputation.
ISPs rate-limit or spam-folder emails from unknown senders.
Warmup builds reputation gradually by starting at low volume with real replies.

## Phase 1 — Domain warmup (Resend, weeks 1-4)

Use real outreach emails during warmup — NOT dummy sends.
Gothenburg vet-intel leads are the warmup traffic once the city is activated.

| Week | Sends/day | Total that week | Notes |
|------|-----------|-----------------|-------|
| 1    | 1         | 5               | Mon-Fri only |
| 2    | 2         | 10              | Never more than 2x previous week |
| 3    | 3         | 15              | |
| 4+   | 5         | 25              | Normal volume — full activation |

Rules:
- Never jump more than 2x the previous week's daily volume
- Keep bounce rate below 2% at all times — if it spikes, pause and investigate
- Aim for at least 20% open rate during warmup (real personalised emails help)
- Space sends by at least 1 hour (already enforced by the engine)

## Phase 2 — Gmail inbox warmup (parallel to domain warmup)

New Gmail accounts are also scrutinised by Google. During warmup:
- The engine sends via Resend (not Gmail SMTP) — Gmail is reply-detection only
- Replies to second-city emails land in the second Gmail inbox
- The IMAP poller handles this automatically once SECOND_GMAIL_ADDRESS is set
- No manual action needed — Gmail reputation builds naturally as replies arrive

## Activation checklist (when ready)

Run these steps in order. Each step is a prerequisite for the next.

### Step 1 — Register and verify second domain
- Register domain (e.g. casautomations.se) at Loopia/Namecheap (~100 SEK/year)
- Add domain to Resend:
  ```
  POST https://api.resend.com/domains
  Authorization: Bearer re_Z5Fn1iB7_LgPZ5MsggZer36fduAMzDo4p
  {"name":"casautomations.se","region":"eu-west-1"}
  ```
- Add the DNS records Resend returns (SPF TXT, DKIM CNAMEs, DMARC TXT)
- Verify: `POST https://api.resend.com/domains/{id}/verify`

### Step 2 — Create second Gmail account
- Create a new Google account (e.g. kasper.gbg@gmail.com or similar)
- Enable 2FA on the account
- Generate an App Password: myaccount.google.com/apppasswords → Mail → Other
- Keep the 16-character app password — you'll need it for Railway

### Step 3 — Set Railway env vars
Add these four vars in Railway → email backend service → Variables:
```
SECOND_GMAIL_ADDRESS      = kasper.gbg@gmail.com
SECOND_GMAIL_APP_PASSWORD = xxxx-xxxx-xxxx-xxxx
SECOND_DOMAIN_FROM        = Kasper <kasper@casautomations.se>
SECOND_DOMAIN_REPLY_TO    = kasper.gbg@gmail.com
```
Railway redeploys automatically. IMAP polling of the second inbox starts immediately.

### Step 4 — Flip city to active in cities.js
Edit `backend/services/cities.js`:
```js
gothenburg: {
  active: true,   // <-- change false to true
  ...
}
```
Commit and push. On next send cycle, Gothenburg leads route through the second domain.

### Step 5 — Follow warmup schedule above
- Week 1: verify 1 email/day sends correctly and replies route to second inbox
- Watch Railway logs for `[IMAP:gothenburg]` confirming second inbox is polled
- Scale up following the table above

## Monitoring during warmup

Check these in Railway logs:
- `[IMAP:gothenburg] Poll completed` — second inbox polling correctly
- `[Resend] Sent to x@y.com` — sends going out
- `[Resend] SEND FAILED` — investigate immediately if domain not yet warmed

Check Resend dashboard for:
- Open rate (target ≥20% during warmup)
- Bounce rate (must stay below 2%)
- Spam complaints (must stay at 0)
