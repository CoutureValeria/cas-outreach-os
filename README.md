# CAS Automations — Cold Email Engine

Cold outreach system for Kasper at CAS Automations. Finds real veterinary clinics in Stockholm, writes hyper-personalised Swedish emails with Claude, and lets Kasper approve every email before it goes out.

---

## Architecture

```
frontend/index.html   → deployed to Vercel (static, no server)
backend/              → deployed to Railway (Node.js Express)
Supabase              → database (free tier)
Gmail SMTP            → email sending via nodemailer
Claude API            → lead research + email generation
```

---

## First-time setup — step by step

### 1. Supabase

1. Go to [supabase.com](https://supabase.com) and create a free project.
2. Open the **SQL Editor** and paste the contents of `database/schema.sql`. Run it.
3. Copy your **Project URL** and **anon public key** from Settings → API.

### 2. Gmail App Password

1. Your sending address is `kaplelbackman@gmail.com`.
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
3. Create an App Password for "Mail". Copy the 16-character password.

### 3. Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com) and create an API key.
2. You need access to `claude-opus-4-5` (for lead sourcing + generation) and `claude-haiku-4-5-20251001` (for follow-up copy).

### 4. Backend — deploy to Railway

1. Create a free account at [railway.app](https://railway.app).
2. Click **New Project → Deploy from GitHub repo**.
3. Point Railway at the `backend/` folder (or push `backend/` as its own repo).
4. In Railway's **Variables** tab, set all of these:

```
ANTHROPIC_API_KEY=your_key_here
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=your_anon_key
GMAIL_ADDRESS=kaplelbackman@gmail.com
GMAIL_APP_PASSWORD=your_16_char_app_password
REPLY_TO=cas@casautomations.com
GOOGLE_SHEET_ID=1OV6cP39wi9MchWaKZKPXfRLNr11JZ
GOOGLE_SERVICE_ACCOUNT_JSON=   (optional — see Google Sheets section below)
BACKEND_API_KEY=pick_any_long_random_string_here
PORT=3001
```

5. Railway will build and deploy automatically. Copy your Railway domain, e.g. `https://cas-engine-production.up.railway.app`.

### 5. Frontend — deploy to Vercel

1. Create a free account at [vercel.com](https://vercel.com).
2. Click **New Project → Import Git Repository** and point it at the `frontend/` folder.
3. No environment variables needed — the frontend talks to your Railway backend directly.
4. After deploy, open the Vercel URL in your browser.

### 6. Connect frontend to backend

1. Open the Vercel URL in your browser.
2. Click ⚙️ **Settings** in the bottom-left.
3. Enter your Railway URL and the `BACKEND_API_KEY` you chose.
4. Click **Test Connection** — you should see "Connected ✓".
5. Done. Everything else works from the dashboard.

---

## Daily workflow for Kasper

1. **Source leads** — click "Source Leads" → set count → Start Search. Claude searches Stockholm for real vet clinics (~1-2 min).
2. **Queue fills** — new leads appear in All Leads with status "New".
3. **Generate emails** — from the queue, click "✍️ Generate Email". Claude writes a personalised Swedish email.
4. **Approve queue** — go to Approval Queue. Read each email. Edit subject/body inline if needed. Click ✅ Approve (or Skip to discard).
5. **Send** — from the Dashboard, click "📨 Send Next Approved". One click = one email goes out. Respects all sending rules automatically (business hours, max 5/day, 1/hour).
6. **Monitor** — Sent Tracker shows everything. Warm Leads shows anyone who replied.

---

## Sending rules (enforced in backend)

| Rule | Value |
|------|-------|
| Max per day | 5 emails (initial + follow-ups combined) |
| Min gap between sends | 1 hour |
| Allowed hours | 08:00–17:00 Stockholm time |
| Allowed days | Monday–Friday only |
| Human approval | Required for every initial email |

---

## Follow-up sequence

- **Day 5** after initial send → one follow-up is sent automatically (during business hours, within daily limit)
- **Day 10** after follow-up → lead is marked "No Response" and the sequence stops
- **Reply detected** → lead instantly becomes a Warm Lead. All future sends for that email stop.
- **Opt-out detected** → added to suppression list. Never contacted again.

---

## Google Sheets sync (optional)

The Sheet (`1OV6cP39wi9MchWaKZKPXfRLNr11JZ`) is used as an external log.

To enable:
1. Create a Service Account in Google Cloud Console.
2. Share the Google Sheet with the service account email (Editor access).
3. Download the JSON key file.
4. In Railway variables, set `GOOGLE_SERVICE_ACCOUNT_JSON` to the entire JSON content on one line.
5. Click "🔄 Sync Sheet" in the dashboard whenever you want to push the sent log.

---

## Reply detection (optional upgrade)

Replies are currently tracked manually via the "Mark as Warm" / "Opt-out" buttons in the Sent Tracker.

To get automatic reply detection:
1. Enable the Gmail API in Google Cloud Console.
2. Create a Pub/Sub topic named `cas-gmail-replies`.
3. Create a push subscription pointing to `https://your-railway-url.app/api/reply-webhook`.
4. Call the Gmail watch API to monitor `kaplelbackman@gmail.com`.
5. Set `WEBHOOK_SECRET` in Railway variables to the token Google includes in push requests.

---

## File structure

```
Email engine/
├── backend/
│   ├── server.js                  Main Express server + all routes
│   ├── package.json
│   ├── railway.json               Railway deployment config
│   ├── .env.example               Copy to .env and fill in values
│   └── services/
│       ├── supabaseClient.js      Shared DB connection
│       ├── leadService.js         Claude web_search → find + verify leads
│       ├── emailService.js        Claude email generation + Gmail SMTP sending
│       ├── schedulerService.js    Cron jobs for follow-ups
│       ├── sheetsService.js       Google Sheets sync
│       └── replyService.js        Gmail reply webhook processing
├── frontend/
│   ├── index.html                 Full dashboard — single file
│   └── vercel.json                Vercel routing config
└── database/
    └── schema.sql                 Run this in Supabase SQL Editor
```

---

## GDPR notes

- This is B2B cold outreach under legitimate interest — not consumer marketing.
- Opt-outs are stored in `opt_outs` table and respected permanently.
- No tracking pixels, no open tracking, no link tracking.
- The opt-out line appears in every email: *"Vill du inte bli kontaktad igen? Svara bara på det här mejlet."*
- Reply opt-out keywords are detected automatically if webhook is configured.

---

## Troubleshooting

**"Outside business hours" when trying to send**
The backend checks the clock in Europe/Stockholm timezone. Sends are only allowed Mon–Fri 08:00–17:00.

**Lead sourcing finds 0 results**
Claude's web_search tool may rate-limit. Try again in a few minutes, or reduce the count.

**Gmail SMTP auth error**
Make sure you're using an App Password, not your Gmail account password. 2FA must be enabled on the Google account.

**Supabase "duplicate key" errors**
Expected — means the lead was already in the DB. The system silently skips duplicates.

**Google Sheets sync fails**
Check that `GOOGLE_SERVICE_ACCOUNT_JSON` is valid JSON on one line and that the service account has Editor access to the Sheet.
