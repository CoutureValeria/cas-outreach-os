/**
 * One-time migration: creates linkedin_leads table in Supabase.
 *
 * Requires SUPABASE_SERVICE_ROLE_KEY (not the anon key — service_role has DDL access).
 * Get it from: Supabase Dashboard → Project Settings → API → service_role key
 *
 * Usage:
 *   SUPABASE_URL=https://tjpkmonazlqmbaazcker.supabase.co \
 *   SUPABASE_SERVICE_ROLE_KEY=eyJ... \
 *   node migrate.js
 */
require('dotenv').config();

const SUPABASE_URL = process.env.SUPABASE_URL;
const SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;

if (!SUPABASE_URL || !SERVICE_ROLE_KEY) {
  console.error('Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY');
  process.exit(1);
}

const SQL = `
CREATE TABLE IF NOT EXISTS linkedin_leads (
  id           uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  clinic_name  text NOT NULL,
  contact_name text,
  title        text,
  linkedin_url text,
  connection_note text,
  status       text NOT NULL DEFAULT 'note_generated',
  area         text DEFAULT 'Stockholm',
  found_at     timestamptz DEFAULT now(),
  sent_at      timestamptz,
  accepted_at  timestamptz,
  notes        text
);

ALTER TABLE linkedin_leads ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'linkedin_leads' AND policyname = 'service_key_full_access'
  ) THEN
    CREATE POLICY "service_key_full_access" ON linkedin_leads USING (true) WITH CHECK (true);
  END IF;
END $$;
`.trim();

async function run() {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/rpc/exec_sql`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'apikey': SERVICE_ROLE_KEY,
      'Authorization': `Bearer ${SERVICE_ROLE_KEY}`,
    },
    body: JSON.stringify({ sql: SQL }),
  });

  if (res.ok) {
    console.log('✓ linkedin_leads table created (or already exists)');
    return;
  }

  const err = await res.json().catch(() => ({}));

  if (err.message?.includes('exec_sql') || err.code === 'PGRST202') {
    console.log('exec_sql function not found — using Management API...');
    await runViaMgmtApi();
  } else {
    console.error('Migration failed:', JSON.stringify(err));
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
    console.log('✓ linkedin_leads table created via Management API');
  } else {
    const err = await res.json().catch(() => ({}));
    console.error('Management API also failed:', JSON.stringify(err));
    console.log('\nRun this SQL manually in the Supabase SQL editor:');
    console.log('https://supabase.com/dashboard/project/' + ref + '/sql');
    console.log('\n' + SQL);
    process.exit(1);
  }
}

run().catch(e => { console.error(e); process.exit(1); });
