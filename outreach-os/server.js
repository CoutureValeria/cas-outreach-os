require('dotenv').config();
const express = require('express');
const helmet = require('helmet');
const cors = require('cors');
const rateLimit = require('express-rate-limit');

const instagramService = require('./services/instagramService');
const linkedinService  = require('./services/linkedinService');

const app = express();
app.set('trust proxy', 1);
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
    const leads = await instagramService.getLeads(req.query.status);
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
    const leads = await linkedinService.getLeads(req.query.status);
    res.json({ leads });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Find decision maker for a single clinic (manual lookup)
app.post('/api/linkedin/find', auth, async (req, res) => {
  try {
    const { clinic_name, area, lead_id, research_notes, primary_pain } = req.body;
    if (!clinic_name) return res.status(400).json({ error: 'clinic_name required' });
    const lead = await linkedinService.findDecisionMaker({ id: lead_id, clinic_name, area, research_notes, primary_pain });
    res.json({ lead });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Bulk: find decision makers for all email engine leads missing a LinkedIn row
app.post('/api/linkedin/find-all', auth, async (req, res) => {
  try {
    const found = await linkedinService.findAllDecisionMakers();
    res.json({ found: found.length, leads: found });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.put('/api/linkedin/leads/:id/status', auth, async (req, res) => {
  try {
    const { status, reply_text } = req.body;
    const VALID = ['new', 'request_sent', 'connected', 'replied', 'not_interested'];
    if (!VALID.includes(status)) return res.status(400).json({ error: 'Invalid status' });
    const lead = await linkedinService.updateStatus(req.params.id, status, reply_text);
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
    const [ig, li] = await Promise.all([instagramService.getStats(), linkedinService.getStats()]);
    res.json({ instagram: ig, linkedin: li });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── Daily action queue ────────────────────────────────────────────────────
// Returns counts for sidebar badges without loading full lead data
app.get('/api/queue/counts', auth, async (req, res) => {
  try {
    const [igNew, liNew, liConn] = await Promise.all([
      instagramService.getLeads('new'),
      linkedinService.getLeads('new'),
      linkedinService.getLeads('connected'),
    ]);

    const threeDaysAgo = Date.now() - 3 * 24 * 60 * 60 * 1000;
    const liFollowUp = liConn.filter(l => {
      const ts = l.accepted_at || l.found_at;
      return ts && new Date(ts).getTime() < threeDaysAgo;
    });

    res.json({
      ig_new:        igNew.length,
      li_new:        liNew.length,
      li_follow_up:  liFollowUp.length,
      total:         igNew.length + liNew.length + liFollowUp.length,
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.listen(PORT, () => {
  console.log(`Outreach OS running on port ${PORT}`);
});
