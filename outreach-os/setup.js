/**
 * setup.js — one-shot Railway + Supabase bootstrap
 *
 * Usage: node outreach-os/setup.js RAILWAY_TOKEN
 *
 * Does:
 *   1. Reads project/env/service IDs from Railway
 *   2. Pulls Supabase + Anthropic keys from the existing email-engine service
 *   3. Runs the linkedin_leads schema migration against Supabase
 *   4. Creates the cas-outreach-os Railway service (if it doesn't exist)
 *   5. Sets all required env vars on the new service
 *   6. Triggers first deployment
 */

const RAILWAY_TOKEN   = process.argv[2];
const RAILWAY_GQL     = 'https://backboard.railway.com/graphql/v2';
const SUPABASE_URL    = 'https://tjpkmonazlqmbaazcker.supabase.co';
const EMAIL_ENGINE_URL = 'https://cas-email-engine-backend-production-3b02.up.railway.app';
const EMAIL_ENGINE_KEY = '1790f2bc89c3b684ae79d51d73d2e0a550797e34c243dd23383d0df70fda6a58';
const OUTREACH_SERVICE_NAME = 'cas-outreach-os';
const GITHUB_REPO = 'CoutureValeria/cas-outreach-os';
const ROOT_DIR = 'outreach-os';

if (!RAILWAY_TOKEN) {
  console.error('\nUsage: node outreach-os/setup.js YOUR_RAILWAY_TOKEN\n');
  console.error('Get your token: https://railway.com/account/tokens → New Token\n');
  process.exit(1);
}

// ── Railway GraphQL helper ────────────────────────────────────────────────
async function gql(query, variables = {}) {
  const r = await fetch(RAILWAY_GQL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${RAILWAY_TOKEN}`,
    },
    body: JSON.stringify({ query, variables }),
  });
  const body = await r.json();
  if (body.errors) throw new Error(body.errors.map(e => e.message).join('; '));
  return body.data;
}

// ── Supabase SQL runner ───────────────────────────────────────────────────
async function runSQL(sql, serviceRoleKey) {
  const headers = {
    'Content-Type': 'application/json',
    'apikey': serviceRoleKey,
    'Authorization': `Bearer ${serviceRoleKey}`,
  };

  // Try exec_sql RPC
  const rpc = await fetch(`${SUPABASE_URL}/rest/v1/rpc/exec_sql`, {
    method: 'POST', headers,
    body: JSON.stringify({ sql }),
  });
  if (rpc.ok) return 'rpc';

  const rpcErr = await rpc.json().catch(() => ({}));
  const notFound = rpcErr.code === 'PGRST202' || (rpcErr.message || '').includes('exec_sql');
  if (!notFound) throw new Error('exec_sql failed: ' + JSON.stringify(rpcErr));

  // Fallback: Management API (needs PAT, service_role won't work — skip gracefully)
  return 'skipped';
}

async function tableExists(key) {
  const r = await fetch(`${SUPABASE_URL}/rest/v1/linkedin_leads?limit=1`, {
    headers: { 'apikey': key, 'Authorization': `Bearer ${key}` },
  });
  return r.ok || r.status === 416; // 416 = range not satisfiable (table exists, just empty)
}

// ── Main ──────────────────────────────────────────────────────────────────
async function main() {
  // ── Step 1: Get Railway project info ─────────────────────────────────
  console.log('\n[1/6] Fetching Railway projects…');
  const { projects } = await gql(`query {
    projects {
      edges { node {
        id name
        services { edges { node { id name } } }
        environments { edges { node { id name } } }
      } }
    }
  }`);

  const allProjects = projects.edges.map(e => e.node);
  if (!allProjects.length) throw new Error('No Railway projects found for this token');

  // Find project that contains the email engine service
  let project, emailService, environment;
  for (const p of allProjects) {
    const svc = p.services.edges.find(e =>
      e.node.name.toLowerCase().includes('email') ||
      e.node.name.toLowerCase().includes('backend')
    );
    if (svc) {
      project = p;
      emailService = svc.node;
      environment = p.environments.edges[0]?.node; // production env
      break;
    }
  }

  if (!project) {
    // Use first project
    project = allProjects[0];
    emailService = project.services.edges[0]?.node;
    environment = project.environments.edges[0]?.node;
  }

  if (!project || !environment) throw new Error('Could not determine project or environment');

  console.log(`    Project:     ${project.name} (${project.id})`);
  console.log(`    Environment: ${environment.name} (${environment.id})`);
  console.log(`    Email svc:   ${emailService?.name || 'not found'} (${emailService?.id || '?'})`);

  // ── Step 2: Read env vars from email engine service ──────────────────
  console.log('\n[2/6] Reading env vars from email engine service…');
  let SUPABASE_ANON_KEY = '';
  let SUPABASE_SERVICE_ROLE_KEY = '';
  let ANTHROPIC_API_KEY = '';

  if (emailService) {
    const { variables } = await gql(`query variables($projectId: String!, $environmentId: String!, $serviceId: String!) {
      variables(projectId: $projectId, environmentId: $environmentId, serviceId: $serviceId)
    }`, {
      projectId: project.id,
      environmentId: environment.id,
      serviceId: emailService.id,
    });

    const vars = variables || {};
    SUPABASE_ANON_KEY         = vars['SUPABASE_ANON_KEY'] || '';
    SUPABASE_SERVICE_ROLE_KEY = vars['SUPABASE_SERVICE_ROLE'] || vars['SUPABASE_SERVICE_ROLE_KEY'] || '';
    ANTHROPIC_API_KEY         = vars['ANTHROPIC_API_KEY'] || '';

    console.log(`    SUPABASE_ANON_KEY:         ${SUPABASE_ANON_KEY ? 'found ✓' : 'NOT FOUND'}`);
    console.log(`    SUPABASE_SERVICE_ROLE_KEY: ${SUPABASE_SERVICE_ROLE_KEY ? 'found ✓' : 'NOT FOUND'}`);
    console.log(`    ANTHROPIC_API_KEY:         ${ANTHROPIC_API_KEY ? 'found ✓' : 'NOT FOUND'}`);
  }

  // Choose best key for DDL
  const ddlKey = SUPABASE_SERVICE_ROLE_KEY || SUPABASE_ANON_KEY;
  if (!ddlKey) {
    console.error('\n    ✗ Neither Supabase key found in Railway env vars.');
    console.error('    Cannot run migration without a key. Skipping Step 3.');
  }

  // ── Step 3: Run Supabase migration ───────────────────────────────────
  const MIGRATION_SQL = `
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
    SELECT 1 FROM pg_policies WHERE tablename='linkedin_leads' AND policyname='service_key_full_access'
  ) THEN
    CREATE POLICY "service_key_full_access" ON linkedin_leads USING (true) WITH CHECK (true);
  END IF;
END $$;
ALTER TABLE linkedin_leads ADD COLUMN IF NOT EXISTS lead_id      uuid;
ALTER TABLE linkedin_leads ADD COLUMN IF NOT EXISTS reply_text   text;
ALTER TABLE linkedin_leads ADD COLUMN IF NOT EXISTS replied_at   timestamptz;
UPDATE linkedin_leads SET status='new'          WHERE status='note_generated';
UPDATE linkedin_leads SET status='request_sent' WHERE status='sent';
UPDATE linkedin_leads SET status='connected'    WHERE status='accepted';
`.trim();

  if (ddlKey) {
    console.log('\n[3/6] Running Supabase migration…');
    const method = await runSQL(MIGRATION_SQL, ddlKey).catch(e => { throw new Error('Migration: ' + e.message); });

    if (method === 'skipped') {
      // exec_sql not available — verify if table already exists
      const exists = await tableExists(SUPABASE_ANON_KEY || ddlKey);
      if (exists) {
        console.log('    exec_sql RPC not available, but linkedin_leads already exists ✓');
      } else {
        console.log('    exec_sql RPC not available and table not found.');
        console.log('    → Run schema SQL manually: https://supabase.com/dashboard/project/tjpkmonazlqmbaazcker/sql');
      }
    } else {
      console.log(`    Migration ran via ${method} ✓`);
      const exists = await tableExists(SUPABASE_ANON_KEY || ddlKey);
      console.log(`    linkedin_leads reachable: ${exists ? 'yes ✓' : 'NO — check RLS policies'}`);
    }
  } else {
    console.log('\n[3/6] Skipping migration (no Supabase key).');
    // Try verify with anon key anyway
    const anonCheck = await tableExists('placeholder').catch(() => false);
    console.log(`    Table exists check skipped.`);
  }

  // ── Step 4: Find or create outreach-os service ───────────────────────
  console.log('\n[4/6] Checking if outreach-os service already exists…');
  const existingService = project.services.edges.find(e =>
    e.node.name.toLowerCase().includes('outreach')
  );

  let outreachServiceId;

  if (existingService) {
    outreachServiceId = existingService.node.id;
    console.log(`    Already exists: ${existingService.node.name} (${outreachServiceId})`);
  } else {
    console.log(`    Creating new service: ${OUTREACH_SERVICE_NAME}…`);
    const { serviceCreate } = await gql(`mutation serviceCreate($input: ServiceCreateInput!) {
      serviceCreate(input: $input) { id name }
    }`, {
      input: {
        projectId: project.id,
        name: OUTREACH_SERVICE_NAME,
        source: { repo: GITHUB_REPO },
      },
    });
    outreachServiceId = serviceCreate.id;
    console.log(`    Created: ${serviceCreate.name} (${outreachServiceId}) ✓`);
  }

  // ── Step 5: Set root directory ────────────────────────────────────────
  console.log('\n[5/6] Setting root directory and env vars…');
  await gql(`mutation serviceInstanceUpdate($serviceId: String!, $environmentId: String!, $input: ServiceInstanceUpdateInput!) {
    serviceInstanceUpdate(serviceId: $serviceId, environmentId: $environmentId, input: $input)
  }`, {
    serviceId: outreachServiceId,
    environmentId: environment.id,
    input: { rootDirectory: ROOT_DIR },
  });
  console.log(`    Root directory set to: ${ROOT_DIR} ✓`);

  // ── Step 6: Set env vars ──────────────────────────────────────────────
  const OUTREACH_OS_API_KEY = 'outreach-os-' + Math.random().toString(36).slice(2, 10);

  const envVars = {
    ANTHROPIC_API_KEY:   ANTHROPIC_API_KEY,
    SUPABASE_URL:        SUPABASE_URL,
    SUPABASE_ANON_KEY:   SUPABASE_ANON_KEY,
    OUTREACH_OS_API_KEY: OUTREACH_OS_API_KEY,
    EMAIL_ENGINE_URL:    EMAIL_ENGINE_URL,
    EMAIL_ENGINE_API_KEY: EMAIL_ENGINE_KEY,
    PORT:                '3002',
  };

  // Set all vars in one call
  await gql(`mutation variableCollectionUpsert($input: VariableCollectionUpsertInput!) {
    variableCollectionUpsert(input: $input)
  }`, {
    input: {
      projectId: project.id,
      environmentId: environment.id,
      serviceId: outreachServiceId,
      variables: envVars,
    },
  });

  const setCount = Object.keys(envVars).filter(k => envVars[k]).length;
  console.log(`    Set ${setCount} env vars ✓`);
  console.log(`    OUTREACH_OS_API_KEY = ${OUTREACH_OS_API_KEY}`);
  if (!ANTHROPIC_API_KEY) console.log('    ⚠  ANTHROPIC_API_KEY was blank — update it in Railway dashboard');
  if (!SUPABASE_ANON_KEY) console.log('    ⚠  SUPABASE_ANON_KEY was blank — update it in Railway dashboard');

  // ── Step 7: Deploy ────────────────────────────────────────────────────
  console.log('\n[6/6] Triggering deployment…');
  try {
    await gql(`mutation serviceInstanceDeployV2($serviceId: String!, $environmentId: String!) {
      serviceInstanceDeployV2(serviceId: $serviceId, environmentId: $environmentId)
    }`, {
      serviceId: outreachServiceId,
      environmentId: environment.id,
    });
    console.log('    Deployment triggered ✓');
  } catch (e) {
    console.log('    Deploy trigger skipped (Railway will auto-deploy on git push): ' + e.message);
  }

  console.log('\n════════════════════════════════════════════════════');
  console.log('Done. Summary:');
  console.log(`  Railway project:  ${project.name}`);
  console.log(`  Outreach service: ${OUTREACH_SERVICE_NAME} (${outreachServiceId})`);
  console.log(`  OUTREACH_OS_API_KEY: ${OUTREACH_OS_API_KEY}`);
  console.log('\nOnce Railway assigns a URL, open dashboard/index.html');
  console.log('→ Settings → paste the Railway URL + the API key above.');
  console.log('════════════════════════════════════════════════════\n');
}

main().catch(e => {
  console.error('\n✗ Error:', e.message, '\n');
  process.exit(1);
});
