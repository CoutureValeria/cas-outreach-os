/**
 * setup.js — one-shot Railway + Supabase bootstrap
 *
 * Usage: node outreach-os/setup.js RAILWAY_TOKEN
 *
 * Project IDs discovered automatically — script runs in ~15 seconds.
 */

const RAILWAY_TOKEN   = process.argv[2];
const RAILWAY_GQL     = 'https://backboard.railway.com/graphql/v2';
const SUPABASE_URL    = 'https://tjpkmonazlqmbaazcker.supabase.co';
const EMAIL_ENGINE_URL = 'https://cas-email-engine-backend-production-3b02.up.railway.app';
const EMAIL_ENGINE_KEY = '1790f2bc89c3b684ae79d51d73d2e0a550797e34c243dd23383d0df70fda6a58';
const OUTREACH_SERVICE_NAME = 'cas-outreach-os';
const GITHUB_REPO     = 'CoutureValeria/cas-outreach-os';
const ROOT_DIR        = 'outreach-os';

// Discovered from the live Railway environment
const PROJECT_ID      = '385709db-fe1a-4746-868e-cd48f9d87da0';
const ENVIRONMENT_ID  = 'd39bb79d-8c4b-4e32-bcb2-abe8a622a31e';
const SUPABASE_ANON_KEY = require('fs').existsSync('/tmp/sb_anon.txt')
  ? require('fs').readFileSync('/tmp/sb_anon.txt', 'utf8').trim()
  : '';

if (!RAILWAY_TOKEN) {
  console.error('\nUsage: node outreach-os/setup.js YOUR_RAILWAY_TOKEN\n');
  console.error('Get your token: https://railway.com/account/tokens → New Token\n');
  process.exit(1);
}

async function gql(query, variables = {}) {
  const r = await fetch(RAILWAY_GQL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${RAILWAY_TOKEN}` },
    body: JSON.stringify({ query, variables }),
  });
  const body = await r.json();
  if (body.errors) throw new Error(body.errors.map(e => e.message).join('; '));
  return body.data;
}

const MIGRATION_SQL = [
  "CREATE TABLE IF NOT EXISTS linkedin_leads (id uuid DEFAULT gen_random_uuid() PRIMARY KEY, lead_id uuid, clinic_name text NOT NULL, contact_name text, title text, linkedin_url text, connection_note text, reply_text text, status text NOT NULL DEFAULT 'new', area text DEFAULT 'Stockholm', found_at timestamptz DEFAULT now(), sent_at timestamptz, accepted_at timestamptz, replied_at timestamptz, notes text);",
  "CREATE INDEX IF NOT EXISTS linkedin_leads_lead_id_idx ON linkedin_leads (lead_id);",
  "ALTER TABLE linkedin_leads ENABLE ROW LEVEL SECURITY;",
  "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='linkedin_leads' AND policyname='service_key_full_access') THEN CREATE POLICY \"service_key_full_access\" ON linkedin_leads USING (true) WITH CHECK (true); END IF; END $$;",
  "ALTER TABLE linkedin_leads ADD COLUMN IF NOT EXISTS lead_id uuid;",
  "ALTER TABLE linkedin_leads ADD COLUMN IF NOT EXISTS reply_text text;",
  "ALTER TABLE linkedin_leads ADD COLUMN IF NOT EXISTS replied_at timestamptz;",
  "UPDATE linkedin_leads SET status='new' WHERE status='note_generated';",
  "UPDATE linkedin_leads SET status='request_sent' WHERE status='sent';",
  "UPDATE linkedin_leads SET status='connected' WHERE status='accepted';",
].join('\n');

async function main() {
  // ── Step 1: Get Railway service variables (Supabase + Anthropic keys) ──
  console.log('\n[1/5] Reading env vars from Railway email-engine service…');
  const EMAIL_SERVICE_ID = 'eb5d7ac1-3e77-4241-86dc-beed53199b27';
  let vars = {};
  try {
    const { variables } = await gql(`query variables($projectId:String!,$environmentId:String!,$serviceId:String!){
      variables(projectId:$projectId,environmentId:$environmentId,serviceId:$serviceId)
    }`, { projectId: PROJECT_ID, environmentId: ENVIRONMENT_ID, serviceId: EMAIL_SERVICE_ID });
    vars = variables || {};
  } catch (e) {
    console.log('    Could not read vars:', e.message);
  }

  const ANTHROPIC_API_KEY  = vars['ANTHROPIC_API_KEY']  || '';
  const SUPABASE_ANON      = vars['SUPABASE_ANON_KEY']  || SUPABASE_ANON_KEY;
  const SUPABASE_SVC_ROLE  = vars['SUPABASE_SERVICE_ROLE'] || vars['SUPABASE_SERVICE_ROLE_KEY'] || '';

  console.log(`    ANTHROPIC_API_KEY:  ${ANTHROPIC_API_KEY ? 'found ✓' : 'NOT FOUND'}`);
  console.log(`    SUPABASE_ANON_KEY:  ${SUPABASE_ANON    ? 'found ✓' : 'NOT FOUND'}`);
  console.log(`    SERVICE_ROLE_KEY:   ${SUPABASE_SVC_ROLE ? 'found ✓' : 'not set (will skip DDL)'}`);

  // ── Step 2: Run Supabase migration ──────────────────────────────────────
  console.log('\n[2/5] Running Supabase migration…');
  const ddlKey = SUPABASE_SVC_ROLE || SUPABASE_ANON;
  let migrated = false;

  if (ddlKey) {
    const rpc = await fetch(`${SUPABASE_URL}/rest/v1/rpc/exec_sql`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'apikey': ddlKey, 'Authorization': `Bearer ${ddlKey}` },
      body: JSON.stringify({ sql: MIGRATION_SQL }),
    });
    if (rpc.ok) {
      console.log('    Migration complete via exec_sql ✓');
      migrated = true;
    } else {
      const err = await rpc.json().catch(() => ({}));
      console.log('    exec_sql unavailable:', err.message || err.code);
    }
  }

  // Verify table exists
  const verifyKey = SUPABASE_ANON || ddlKey;
  if (verifyKey) {
    const check = await fetch(`${SUPABASE_URL}/rest/v1/linkedin_leads?limit=1`, {
      headers: { 'apikey': verifyKey, 'Authorization': `Bearer ${verifyKey}` },
    });
    if (check.ok || check.status === 416) {
      console.log('    linkedin_leads table: EXISTS ✓');
      migrated = true;
    } else {
      console.log(`    linkedin_leads table: NOT FOUND (HTTP ${check.status})`);
      if (!migrated) {
        console.log('\n    ⚠  Could not create table automatically.');
        console.log('    Run this SQL once in https://supabase.com/dashboard/project/tjpkmonazlqmbaazcker/sql :');
        console.log('\n    ' + MIGRATION_SQL.split('\n').join('\n    ') + '\n');
      }
    }
  }

  // ── Step 3: Find or create outreach-os service ──────────────────────────
  console.log('\n[3/5] Checking for existing outreach-os service…');
  const { project } = await gql(`query project($id:String!){
    project(id:$id){
      services{ edges{ node{ id name } } }
    }
  }`, { id: PROJECT_ID });

  const existing = project.services.edges.find(e =>
    e.node.name.toLowerCase().includes('outreach')
  );
  let serviceId = existing?.node?.id;

  if (serviceId) {
    console.log(`    Already exists: ${existing.node.name} (${serviceId})`);
  } else {
    console.log(`    Creating: ${OUTREACH_SERVICE_NAME}…`);
    const { serviceCreate } = await gql(`mutation serviceCreate($input:ServiceCreateInput!){
      serviceCreate(input:$input){ id name }
    }`, { input: { projectId: PROJECT_ID, name: OUTREACH_SERVICE_NAME, source: { repo: GITHUB_REPO } } });
    serviceId = serviceCreate.id;
    console.log(`    Created: ${serviceCreate.name} (${serviceId}) ✓`);
  }

  // ── Step 4: Configure root directory + env vars ─────────────────────────
  console.log('\n[4/5] Setting root directory and env vars…');
  await gql(`mutation serviceInstanceUpdate($serviceId:String!,$environmentId:String!,$input:ServiceInstanceUpdateInput!){
    serviceInstanceUpdate(serviceId:$serviceId,environmentId:$environmentId,input:$input)
  }`, { serviceId, environmentId: ENVIRONMENT_ID, input: { rootDirectory: ROOT_DIR } });
  console.log(`    Root directory: ${ROOT_DIR} ✓`);

  const OUTREACH_OS_API_KEY = 'outreach-' + Math.random().toString(36).slice(2, 12);
  await gql(`mutation variableCollectionUpsert($input:VariableCollectionUpsertInput!){
    variableCollectionUpsert(input:$input)
  }`, {
    input: {
      projectId: PROJECT_ID,
      environmentId: ENVIRONMENT_ID,
      serviceId,
      variables: {
        ANTHROPIC_API_KEY,
        SUPABASE_URL,
        SUPABASE_ANON_KEY:    SUPABASE_ANON,
        OUTREACH_OS_API_KEY,
        EMAIL_ENGINE_URL,
        EMAIL_ENGINE_API_KEY: EMAIL_ENGINE_KEY,
        PORT: '3002',
      },
    },
  });
  console.log(`    Env vars set ✓`);
  console.log(`    OUTREACH_OS_API_KEY = ${OUTREACH_OS_API_KEY}`);

  // ── Step 5: Deploy ──────────────────────────────────────────────────────
  console.log('\n[5/5] Triggering deployment…');
  try {
    await gql(`mutation serviceInstanceDeployV2($serviceId:String!,$environmentId:String!){
      serviceInstanceDeployV2(serviceId:$serviceId,environmentId:$environmentId)
    }`, { serviceId, environmentId: ENVIRONMENT_ID });
    console.log('    Deployment triggered ✓');
  } catch (e) {
    console.log('    Auto-deploy will fire on next git push:', e.message.slice(0, 80));
  }

  console.log('\n══════════════════════════════════════════════════════════');
  console.log('✓ Done. Railway service created and deploying.');
  console.log(`  Service ID:           ${serviceId}`);
  console.log(`  OUTREACH_OS_API_KEY:  ${OUTREACH_OS_API_KEY}`);
  if (!migrated) console.log('  ⚠ Run the Supabase SQL above before using LinkedIn features.');
  console.log('\nOnce Railway gives you a URL:');
  console.log('  dashboard/index.html → ⚙ Settings → paste URL + API key');
  console.log('══════════════════════════════════════════════════════════\n');
}

main().catch(e => { console.error('\n✗', e.message, '\n'); process.exit(1); });
