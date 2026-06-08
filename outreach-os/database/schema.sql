-- Outreach OS: LinkedIn leads table
-- Run this once in Supabase SQL editor

CREATE TABLE IF NOT EXISTS linkedin_leads (
  id         uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  clinic_name     text NOT NULL,
  contact_name    text,
  title           text,
  linkedin_url    text,
  connection_note text,
  status     text NOT NULL DEFAULT 'note_generated',
  area       text DEFAULT 'Stockholm',
  found_at   timestamptz DEFAULT now(),
  sent_at    timestamptz,
  accepted_at timestamptz,
  notes      text
);

-- status values: note_generated → sent → accepted → replied → not_interested

ALTER TABLE linkedin_leads ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_key_full_access" ON linkedin_leads
  USING (true) WITH CHECK (true);
