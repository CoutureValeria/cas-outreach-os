-- Outreach OS: LinkedIn leads table
-- Run this once in Supabase SQL editor

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

-- status values: new → request_sent → connected → replied → not_interested

-- Index for fast lookup by email engine lead id
CREATE INDEX IF NOT EXISTS linkedin_leads_lead_id_idx ON linkedin_leads (lead_id);

ALTER TABLE linkedin_leads ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_key_full_access" ON linkedin_leads
  USING (true) WITH CHECK (true);

-- Migration: run if table already exists with old schema
ALTER TABLE linkedin_leads ADD COLUMN IF NOT EXISTS lead_id      uuid;
ALTER TABLE linkedin_leads ADD COLUMN IF NOT EXISTS reply_text   text;
ALTER TABLE linkedin_leads ADD COLUMN IF NOT EXISTS replied_at   timestamptz;

-- Migrate old status values to new names (idempotent)
UPDATE linkedin_leads SET status = 'new'          WHERE status = 'note_generated';
UPDATE linkedin_leads SET status = 'request_sent' WHERE status = 'sent';
UPDATE linkedin_leads SET status = 'connected'    WHERE status = 'accepted';
