const Anthropic = require('@anthropic-ai/sdk');
const { createClient } = require('@supabase/supabase-js');

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_ANON_KEY);

async function findDecisionMaker(clinic_name, area = 'Stockholm') {
  const existing = await supabase
    .from('linkedin_leads')
    .select('*')
    .ilike('clinic_name', clinic_name)
    .maybeSingle();

  if (existing.data) return existing.data;

  const prompt = `Search LinkedIn for the owner, clinic director, or practice manager of the veterinary clinic "${clinic_name}" in ${area}, Sweden.

Return a JSON object:
{
  "contact_name": "First Last or null",
  "title": "job title or null",
  "linkedin_url": "https://linkedin.com/in/... or null",
  "connection_note": "a short Swedish LinkedIn connection note (max 300 chars)"
}

For the connection_note, use this style:
"Hej [Name/du], jag såg att du driver [Clinic] — vi hjälper veterinärkliniker i Stockholm med automatiserad bokningshantering. Kul att koppla!"

If you cannot find a specific person, set contact_name and linkedin_url to null but still generate a generic connection_note.
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
    result.connection_note = `Hej, jag såg att du driver ${clinic_name} — vi hjälper veterinärkliniker i Stockholm med automatiserad bokningshantering. Kul att koppla!`;
  }

  const row = {
    clinic_name,
    area,
    contact_name: result.contact_name,
    title: result.title,
    linkedin_url: result.linkedin_url,
    connection_note: result.connection_note,
    status: 'note_generated',
  };

  const { data, error } = await supabase.from('linkedin_leads').insert(row).select().single();
  if (error) throw new Error(error.message);
  return data;
}

async function getLeads(status) {
  let q = supabase.from('linkedin_leads').select('*').order('found_at', { ascending: false });
  if (status) q = q.eq('status', status);
  const { data, error } = await q;
  if (error) throw new Error(error.message);
  return data || [];
}

async function updateStatus(id, status) {
  const update = { status };
  if (status === 'sent') update.sent_at = new Date().toISOString();
  if (status === 'accepted') update.accepted_at = new Date().toISOString();
  const { data, error } = await supabase.from('linkedin_leads').update(update).eq('id', id).select().single();
  if (error) throw new Error(error.message);
  return data;
}

async function updateNotes(id, notes) {
  const { data, error } = await supabase.from('linkedin_leads').update({ notes }).eq('id', id).select().single();
  if (error) throw new Error(error.message);
  return data;
}

async function getStats() {
  const { data } = await supabase.from('linkedin_leads').select('status');
  const counts = { total: 0, sent: 0, accepted: 0, replied: 0 };
  for (const row of data || []) {
    counts.total++;
    if (row.status === 'sent') counts.sent++;
    if (row.status === 'accepted') counts.accepted++;
    if (row.status === 'replied') counts.replied++;
  }
  counts.accept_rate = counts.sent > 0 ? Math.round((counts.accepted / counts.sent) * 100) : 0;
  counts.reply_rate = counts.accepted > 0 ? Math.round((counts.replied / counts.accepted) * 100) : 0;
  return counts;
}

module.exports = { findDecisionMaker, getLeads, updateStatus, updateNotes, getStats };
