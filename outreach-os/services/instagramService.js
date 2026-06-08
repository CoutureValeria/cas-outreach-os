const Anthropic = require('@anthropic-ai/sdk');
const { createClient } = require('@supabase/supabase-js');

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_ANON_KEY);

const DM_TEMPLATE = 'Hej, lite nyfiken bara — hanterar ni bokningsförfrågningar som kommer in via Instagram?';

const SEARCH_QUERIES = [
  'veterinärklinik Södermalm instagram',
  'djurklinik Bromma instagram',
  'veterinär Nacka instagram',
  'veterinärklinik Täby instagram',
  'djurklinik Lidingö instagram',
  'veterinär Kungsholmen instagram',
  'djurklinik Järfälla instagram',
  'veterinärklinik Huddinge instagram',
  'veterinär Solna instagram',
  'djurklinik Vasastan instagram',
  'veterinär Östermalm instagram',
  'djurklinik Sundbyberg instagram',
  'veterinärklinik Farsta instagram',
  'veterinär Stockholm site:instagram.com',
];

function normaliseHandle(raw) {
  if (!raw) return null;
  return raw
    .replace(/^@/, '')
    .replace(/https?:\/\/(?:www\.)?instagram\.com\/?/i, '')
    .replace(/\/$/, '')
    .toLowerCase()
    .trim();
}

function shuffle(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

async function searchOneQuery(query, existingHandles) {
  const prompt = `Search for Instagram handles of veterinary clinics in Stockholm, Sweden using this query: "${query}".

Return a JSON array of objects: [{"handle":"@clinichandle","clinic_name":"Clinic Name","area":"Stockholm neighbourhood"}]
Rules:
- Only real Instagram handles you found in search results (format: @username or instagram.com/username)
- Only veterinary clinics (veterinär, djurklinik, smådjursklinik) in Stockholm area
- Return [] if nothing found
Return only the JSON array, no other text.`;

  try {
    const response = await anthropic.messages.create({
      model: 'claude-opus-4-7',
      max_tokens: 1024,
      tools: [{ type: 'web_search_20250305', name: 'web_search' }],
      messages: [{ role: 'user', content: prompt }],
    });

    const textBlock = response.content.find(b => b.type === 'text');
    if (!textBlock) return [];

    const match = textBlock.text.match(/\[[\s\S]*\]/);
    if (!match) return [];
    const parsed = JSON.parse(match[0]);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

async function findHandles(count = 8) {
  const { data: existing } = await supabase.from('instagram_leads').select('handle');
  const existingHandles = new Set((existing || []).map(r => normaliseHandle(r.handle)));

  const queries = shuffle([...SEARCH_QUERIES]).slice(0, Math.min(count + 3, SEARCH_QUERIES.length));
  const found = [];

  for (const query of queries) {
    if (found.length >= count) break;
    const results = await searchOneQuery(query, existingHandles);
    for (const result of results) {
      if (found.length >= count) break;
      const normalised = normaliseHandle(result.handle);
      if (!normalised || existingHandles.has(normalised)) continue;
      existingHandles.add(normalised);
      found.push({ ...result, handle: '@' + normalised });
    }
  }

  if (found.length === 0) return [];

  const rows = found.map(f => ({
    handle: f.handle,
    clinic_name: f.clinic_name || '',
    area: f.area || 'Stockholm',
    status: 'new',
  }));

  const { data, error } = await supabase.from('instagram_leads').upsert(rows, { onConflict: 'handle' }).select();
  if (error) throw new Error(error.message);
  return data;
}

async function getLeads(status) {
  let q = supabase.from('instagram_leads').select('*').order('found_at', { ascending: false });
  if (status) q = q.eq('status', status);
  const { data, error } = await q;
  if (error) throw new Error(error.message);
  return data || [];
}

async function updateStatus(id, status, reply_text) {
  const update = { status };
  if (status === 'dm_sent') update.dm_sent_at = new Date().toISOString();
  if (status === 'replied') {
    update.replied_at = new Date().toISOString();
    if (reply_text) update.reply_text = reply_text;
  }
  const { data, error } = await supabase.from('instagram_leads').update(update).eq('id', id).select().single();
  if (error) throw new Error(error.message);
  return data;
}

async function updateNotes(id, notes) {
  const { data, error } = await supabase.from('instagram_leads').update({ notes }).eq('id', id).select().single();
  if (error) throw new Error(error.message);
  return data;
}

async function getStats() {
  const { data } = await supabase.from('instagram_leads').select('status');
  const counts = { total: 0, dm_sent: 0, replied: 0, warm: 0 };
  for (const row of data || []) {
    counts.total++;
    if (row.status === 'dm_sent') counts.dm_sent++;
    if (row.status === 'replied' || row.status === 'warm') {
      counts.replied++;
      if (row.status === 'warm') counts.warm++;
    }
  }
  counts.reply_rate = counts.dm_sent > 0 ? Math.round((counts.replied / counts.dm_sent) * 100) : 0;
  return counts;
}

module.exports = { findHandles, getLeads, updateStatus, updateNotes, getStats, DM_TEMPLATE };
