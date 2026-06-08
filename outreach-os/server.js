require('dotenv').config();
const express = require('express');
const helmet = require('helmet');
const cors = require('cors');
const rateLimit = require('express-rate-limit');

const instagramService = require('./services/instagramService');
const linkedinService = require('./services/linkedinService');

const app = express();
const PORT = process.env.PORT || 3002;
const API_KEY = process.env.OUTREACH_OS_API_KEY;

app.use(helmet({ contentSecurityPolicy: false }));
app.use(cors());
app.use(express.json());

const limiter = rateLimit({ windowMs: 60_000, max: 120 });
app.use('/api/', limiter);

function auth(req, res, next) {
  if (!API_KEY) return next();
  const key = req.headers['x-api-key'];
  if (key !== API_KEY) return res.status(401).json({ error: 'Unauthorized' });
  next();
}

// ── Health ────────────────────────────────────────────────────────────────
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'cas-outreach-os', ts: new Date().toISOString() });
});

// ── Instagram ─────────────────────────────────────────────────────────────
app.get('/api/instagram/leads', auth, async (req, res) => {
  try {
    const { status } = req.query;
    const leads = await instagramService.getLeads(status);
    res.json({ leads });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/instagram/find', auth, async (req, res) => {
  try {
    const count = parseInt(req.body.count) || 8;
    const found = await instagramService.findHandles(count);
    res.json({ found: found.length, leads: found });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.put('/api/instagram/leads/:id/status', auth, async (req, res) => {
  try {
    const { status, reply_text } = req.body;
    const VALID = ['new', 'dm_sent', 'replied', 'warm', 'not_interested', 'opted_out'];
    if (!VALID.includes(status)) return res.status(400).json({ error: 'Invalid status' });
    const lead = await instagramService.updateStatus(req.params.id, status, reply_text);
    res.json({ lead });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.put('/api/instagram/leads/:id/notes', auth, async (req, res) => {
  try {
    const lead = await instagramService.updateNotes(req.params.id, req.body.notes);
    res.json({ lead });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── LinkedIn ──────────────────────────────────────────────────────────────
app.get('/api/linkedin/leads', auth, async (req, res) => {
  try {
    const { status } = req.query;
    const leads = await linkedinService.getLeads(status);
    res.json({ leads });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/linkedin/find', auth, async (req, res) => {
  try {
    const { clinic_name, area } = req.body;
    if (!clinic_name) return res.status(400).json({ error: 'clinic_name required' });
    const lead = await linkedinService.findDecisionMaker(clinic_name, area);
    res.json({ lead });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.put('/api/linkedin/leads/:id/status', auth, async (req, res) => {
  try {
    const { status } = req.body;
    const VALID = ['new', 'note_generated', 'sent', 'accepted', 'replied', 'not_interested'];
    if (!VALID.includes(status)) return res.status(400).json({ error: 'Invalid status' });
    const lead = await linkedinService.updateStatus(req.params.id, status);
    res.json({ lead });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.put('/api/linkedin/leads/:id/notes', auth, async (req, res) => {
  try {
    const lead = await linkedinService.updateNotes(req.params.id, req.body.notes);
    res.json({ lead });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── Analytics ─────────────────────────────────────────────────────────────
app.get('/api/analytics', auth, async (req, res) => {
  try {
    const ig = await instagramService.getStats();
    const li = await linkedinService.getStats();
    res.json({ instagram: ig, linkedin: li });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.listen(PORT, () => {
  console.log(`Outreach OS running on port ${PORT}`);
});
