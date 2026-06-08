/**
 * One-time migration: creates / upgrades linkedin_leads table in Supabase.
 *
 * Requires the SERVICE ROLE key (not the anon key — service_role has DDL access).
 * Get it from: Supabase Dashboard → Project Settings → API → service_role (secret)
 *
 * Usage:
 *   SUPABASE_SERVICE_ROLE_KEY=eyJ... node outreach-os/migrate.js
 *
 * Or if running from inside the outreach-os directory:
 *   SUPABASE_SERVICE_ROLE_KEY=eyJ... node migrate.js
 */
require('dotenv').config({ path: require('path').join(__dirname, '../backend/.env') });

const SUPABASE_URL      = process.env.SUPABASE_URL || 'https://tjpkmonazlqmbaazcker.supabase.co';
const SERVICE_ROLE_KEY  = process.env.SUPABASE_SERVICE_ROLE_KEY;

if (!SERVICE_ROLE_KEY) {
  console.error('\nMissing SUPABASE_SERVICE_ROLE_KEY.\n');
  console.error('Get it from: https://supabase.com/dashboard/project/tjpkmonazlqmbaazcker/settings/api');
  console.error('Then run:');
  console.error('  SUPABASE_SERVICE_ROLE_KEY=eyJ... node outreach-os/migrate.js\n');
  process.exit(1);
}

const SQL = `
CREATE TABLE IF NOT EXISTS linkedin_leads (
  id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  lead_id         uuid,
  clinic_name     text NOT NULL,
  contact_name    text,
  title           text,
  linkedin_url    text,
  connection_note text,
  reply_text      text,
  status          text NOT NULL DEFAULT 'new',
  area            text DEFAULT 'Stockholm',
  found_at        timestamptz DEFAULT now(),
  sent_at         timestamptz,
  accepted_at     timestamptz,
  replied_at      timestamptz,
  notes           text
);

CREATE INDEX IF NOT EXISTS linkedin_leads_lead_id_idx ON linkedin_leads (lead_id);

ALTER TABLE linkedin_leads ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'linkedin_leads' AND policyname = 'service_key_full_access'
  ) THEN
    CREATE POLICY "service_key_full_access" ON linkedin_leads USING (true) WITH CHECK (true);
  END IF;
END $$;

ALTER TABLE linkedin_leads ADD COLUMN IF NOT EXISTS lead_id      uuid;
ALTER TABLE linkedin_leads ADD COLUMN IF NOT EXISTS reply_text   text;
ALTER TABLE linkedin_leads ADD COLUMN IF NOT EXISTS replied_at   timestamptz;

UPDATE linkedin_leads SET status = 'new'          WHERE status = 'note_generated';
UPDATE linkedin_leads SET status = 'request_sent' WHERE status = 'sent';
UPDATE linkedin_leads SET status = 'connected'    WHERE status = 'accepted';
`.trim();

async function run() {
  const headers = {
    'Content-Type': 'application/json',
    'apikey': SERVICE_ROLE_KEY,
    'Authorization': `Bearer ${SERVICE_ROLE_KEY}`,
  };

  // Try exec_sql RPC first
  const rpc = await fetch(`${SUPABASE_URL}/rest/v1/rpc/exec_sql`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ sql: SQL }),
  });

  if (rpc.ok) {
    console.log('✓ linkedin_leads table created / upgraded via exec_sql');
    await verify(headers);
    return;
  }

  const rpcErr = await rpc.json().catch(() => ({}));

  if (rpcErr.code === 'PGRST202' || rpcErr.message?.includes('exec_sql')) {
    console.log('exec_sql not available — trying Management API...');
    await runViaMgmtApi();
  } else {
    console.error('exec_sql failed:', JSON.stringify(rpcErr));
    console.log('\nFallback: run this SQL manually at:');
    console.log('https://supabase.com/dashboard/project/tjpkmonazlqmbaazcker/sql\n');
    console.log(SQL);
    process.exit(1);
  }
}

async function runViaMgmtApi() {
  const ref = new URL(SUPABASE_URL).hostname.split('.')[0];
  const res = await fetch(`https://api.supabase.com/v1/projects/${ref}/database/query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${SERVICE_ROLE_KEY}`,
    },
    body: JSON.stringify({ query: SQL }),
  });

  if (res.ok) {
    console.log('✓ linkedin_leads table created / upgraded via Management API');
    await verify({ 'apikey': SERVICE_ROLE_KEY, 'Authorization': `Bearer ${SERVICE_ROLE_KEY}` });
    return;
  }

  const err = await res.json().catch(() => ({}));
  console.error('Management API failed:', JSON.stringify(err));
  console.log('\nRun this SQL manually at:');
  console.log('https://supabase.com/dashboard/project/tjpkmonazlqmbaazcker/sql\n');
  console.log(SQL);
  process.exit(1);
}

async function verify(headers) {
  const r = await fetch(`${SUPABASE_URL}/rest/v1/linkedin_leads?limit=1`, { headers });
  if (r.ok) {
    const rows = await r.json();
    console.log(`✓ Verified: linkedin_leads is reachable (${rows.length} rows)`);
  } else {
    console.warn('⚠ Table may exist but verification request returned', r.status);
  }
}

run().catch(e => { console.error(e); process.exit(1); });
