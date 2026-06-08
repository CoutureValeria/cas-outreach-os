# CAS Outreach OS

Instagram & LinkedIn outreach service for CAS Automations. Runs alongside the email engine as a separate Express service on port 3002.

## Setup

```bash
cd outreach-os
cp .env.example .env
# fill in .env
npm install
npm start
```

## Database

Run `database/schema.sql` once in Supabase SQL editor to create the `linkedin_leads` table. The `instagram_leads` table is already created by the email engine.

## Environment Variables

| Variable | Description |
|---|---|
| `PORT` | Default 3002 |
| `OUTREACH_OS_API_KEY` | Required on all /api routes via `X-API-Key` header |
| `ANTHROPIC_API_KEY` | Claude API key for handle/decision-maker finding |
| `SUPABASE_URL` | Same Supabase instance as email engine |
| `SUPABASE_ANON_KEY` | Supabase anon key |
| `EMAIL_ENGINE_URL` | Email engine base URL (used by dashboard) |
| `EMAIL_ENGINE_API_KEY` | Email engine API key (used by dashboard) |

## API Routes

All `/api/*` routes require `X-API-Key` header.

### Instagram
| Method | Route | Description |
|---|---|---|
| `GET` | `/api/instagram/leads` | List all leads (optional `?status=dm_sent`) |
| `POST` | `/api/instagram/find` | Find new handles via Claude web search |
| `PUT` | `/api/instagram/leads/:id/status` | Update status + optional reply_text |
| `PUT` | `/api/instagram/leads/:id/notes` | Update notes |

Instagram statuses: `new → dm_sent → replied → warm / not_interested / opted_out`

### LinkedIn
| Method | Route | Description |
|---|---|---|
| `GET` | `/api/linkedin/leads` | List all leads (optional `?status=sent`) |
| `POST` | `/api/linkedin/find` | Find decision maker for `{ clinic_name, area }` |
| `PUT` | `/api/linkedin/leads/:id/status` | Update status |
| `PUT` | `/api/linkedin/leads/:id/notes` | Update notes |

LinkedIn statuses: `note_generated → sent → accepted → replied / not_interested`

### Analytics
| Method | Route | Description |
|---|---|---|
| `GET` | `/api/analytics` | Stats for Instagram and LinkedIn |

## Deploy to Railway

1. Create new Railway service pointing to this repo
2. Set all env vars in Railway dashboard
3. Railway auto-detects Node.js and runs `node server.js`
