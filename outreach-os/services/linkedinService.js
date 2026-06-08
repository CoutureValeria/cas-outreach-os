const Anthropic = require('@anthropic-ai/sdk');
const { createClient } = require('@supabase/supabase-js');

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_ANON_KEY);

const PAIN_PHRASES = {
  phone_overload:     'hanterar mycket bokningar via telefon',
  no_online_booking:  'inte har onlinebokning',
  manual_scheduling:  'jobbar med manuell schemaläggning',
  no_website:         'saknar hemsida',
  slow_response:      'svarar långsamt på förfrågningar',
};

function painToSwedish(pain) {
  return PAIN_PHRASES[pain] || 'hanterar bokningar manuellt';
}

async function findDecisionMaker(lead) {
  const { id: lead_id, clinic_name, area = 'Stockholm', research_notes, primary_pain } = lead;

  const { data: existing } = await supabase
    .from('linkedin_leads')
    .select('*')
    .eq('lead_id', lead_id)
    .maybeSingle();

  if (existing) return existing;

  const painContext = primary_pain
    ? `The clinic's main pain point is: ${primary_pain}.`
    : '';
  const notesContext = research_notes
    ? `Research notes: ${research_notes.slice(0, 400)}`
    : '';

  const prompt = `Search LinkedIn for the owner, clinic director (klinikchef), or head vet of the veterinary clinic "${clinic_name}" in ${area}, Sweden.

${painContext}
${notesContext}

Return a JSON object:
{
  "contact_name": "First Last or null",
  "title": "job title in Swedish or null",
  "linkedin_url": "https://linkedin.com/in/... or null",
  "connection_note": "SHORT Swedish LinkedIn connection note, max 300 chars, 1-2 sentences"
}

For connection_note rules:
- Reference the specific pain: "${painToSwedish(primary_pain)}"
- Sound like a genuine human, not a vendor pitch
- Never mention AI, AI-receptionist, or automation technology by name
- Address them by first name if found, otherwise use "du"
- Example style: "Hej [name], såg att [clinic] ${painToSwedish(primary_pain)} — jobbar med en lösning för just det. Skulle gärna connecta."

Return only the JSON object, no other text.`;

  let result = { contact_name: null, title: null, linkedin_url: null, connection_note: null };

  try {
    const response = await anthropic.messages.create({
      model: 'claude-opus-4-7',
      max_tokens: 1024,
      tools: [{ type: 'web_search_20250305', name: 'web_search' }],
      messages: [{ role: 'user', content: prompt }],
    });

    const textBlock = response.content.find(b => b.type === 'text');
    if (textBlock) {
      const match = textBlock.text.match(/\{[\s\S]*\}/);
      if (match) result = { ...result, ...JSON.parse(match[0]) };
    }
  } catch {
    const painPhrase = painToSwedish(primary_pain);
    const name = result.contact_name ? result.contact_name.split(' ')[0] : 'du';
    result.connection_note = `Hej ${name}, såg att ${clinic_name} ${painPhrase} — jobbar med en lösning för just det. Skulle gärna connecta.`;
  }

  const row = {
    lead_id,
    clinic_name,
    area,
    contact_name: result.contact_name,
    title: result.title,
    linkedin_url: result.linkedin_url,
    connection_note: result.connection_note,
    status: 'new',
  };

  const { data, error } = await supabase.from('linkedin_leads').insert(row).select().single();
  if (error) throw new Error(error.message);
  return data;
}

async function findAllDecisionMakers() {
  const emailUrl  = process.env.EMAIL_ENGINE_URL;
  const emailKey  = process.env.EMAIL_ENGINE_API_KEY;
  if (!emailUrl) throw new Error('EMAIL_ENGINE_URL env var not set');

  const headers = { 'Content-Type': 'application/json' };
  if (emailKey) headers['X-API-Key'] = emailKey;

  const r = await fetch(`${emailUrl}/api/leads`, { headers });
  if (!r.ok) throw new Error(`Email engine returned ${r.status}`);
  const body = await r.json();
  const leads = body.leads || body || [];

  const { data: existing } = await supabase
    .from('linkedin_leads')
    .select('lead_id')
    .not('lead_id', 'is', null);

  const doneIds = new Set((existing || []).map(r => r.lead_id));
  const todo = leads.filter(l => l.id && !doneIds.has(l.id)).slice(0, 10);

  const results = [];
  for (const lead of todo) {
    try {
      const found = await findDecisionMaker(lead);
      results.push(found);
    } catch {}
  }
  return results;
}

async function getLeads(status) {
  let q = supabase.from('linkedin_leads').select('*').order('found_at', { ascending: false });
  if (status) q = q.eq('status', status);
  const { data, error } = await q;
  if (error) throw new Error(error.message);
  return data || [];
}

async function updateStatus(id, status, reply_text) {
  const update = { status };
  if (status === 'request_sent') update.sent_at      = new Date().toISOString();
  if (status === 'connected')    update.accepted_at   = new Date().toISOString();
  if (status === 'replied') {
    update.replied_at = new Date().toISOString();
    if (reply_text) update.reply_text = reply_text;
  }
  const { data, error } = await supabase.from('linkedin_leads').update(update).eq('id', id).select().single();
  if (error) throw new Error(error.message);

  if (status === 'replied' && data.lead_id) {
    await syncWarmToEmailEngine(data.lead_id, reply_text).catch(() => {});
  }

  return data;
}

async function updateNotes(id, notes) {
  const { data, error } = await supabase.from('linkedin_leads').update({ notes }).eq('id', id).select().single();
  if (error) throw new Error(error.message);
  return data;
}

async function syncWarmToEmailEngine(lead_id, replyText) {
  const emailUrl = process.env.EMAIL_ENGINE_URL;
  const emailKey = process.env.EMAIL_ENGINE_API_KEY;
  if (!emailUrl) return;
  const headers = { 'Content-Type': 'application/json' };
  if (emailKey) headers['X-API-Key'] = emailKey;
  await fetch(`${emailUrl}/api/leads/${lead_id}/mark-warm`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ replyText: replyText || 'LinkedIn reply' }),
  });
}

async function getStats() {
  const { data } = await supabase.from('linkedin_leads').select('status');
  const counts = { total: 0, request_sent: 0, connected: 0, replied: 0 };
  for (const row of data || []) {
    counts.total++;
    if (row.status === 'request_sent') counts.request_sent++;
    if (row.status === 'connected')    counts.connected++;
    if (row.status === 'replied')      counts.replied++;
  }
  counts.accept_rate = counts.request_sent > 0 ? Math.round((counts.connected / counts.request_sent) * 100) : 0;
  counts.reply_rate  = counts.connected > 0    ? Math.round((counts.replied   / counts.connected)    * 100) : 0;
  return counts;
}

module.exports = { findDecisionMaker, findAllDecisionMakers, getLeads, updateStatus, updateNotes, getStats };
