-- Example schema for the template.
-- This runs automatically when using the included Postgres container.

CREATE TABLE IF NOT EXISTS notes (
  id          BIGSERIAL PRIMARY KEY,
  title       TEXT NOT NULL,
  body        TEXT NOT NULL DEFAULT '',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO notes (title, body)
VALUES ('Hello from Postgres', 'If you see this in the UI, DB + API + UI are wired up!')
ON CONFLICT DO NOTHING;
