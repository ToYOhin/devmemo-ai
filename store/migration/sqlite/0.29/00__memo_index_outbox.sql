-- memo_index_outbox is the Memos-owned delivery record for rebuildable memo-v1 state.
-- It is dormant until an explicitly authorized lifecycle integration uses it.
CREATE TABLE memo_index_outbox (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id        TEXT    NOT NULL UNIQUE,
  memo_uid        TEXT    NOT NULL,
  source_sequence INTEGER NOT NULL CHECK (source_sequence > 0),
  event_type      TEXT    NOT NULL CHECK (event_type IN (
    'memo.index.requested.v1',
    'memo.reindex.requested.v1',
    'memo.delete.requested.v1'
  )),
  index_version   TEXT    NOT NULL CHECK (index_version = 'memo-v1'),
  operation       TEXT    NOT NULL CHECK (operation IN ('upsert', 'delete')),
  reason          TEXT    NOT NULL,
  occurred_at     TEXT    NOT NULL,
  document        TEXT,
  document_hash   TEXT,
  status          TEXT    NOT NULL CHECK (status IN ('PENDING', 'ACKNOWLEDGED', 'EXHAUSTED')) DEFAULT 'PENDING',
  attempts        INTEGER NOT NULL CHECK (attempts >= 0 AND attempts <= 3) DEFAULT 0,
  last_error_code TEXT,
  created_ts      BIGINT  NOT NULL DEFAULT (strftime('%s', 'now')),
  updated_ts      BIGINT  NOT NULL DEFAULT (strftime('%s', 'now')),
  UNIQUE (memo_uid, index_version, source_sequence),
  CHECK (last_error_code IS NULL OR length(last_error_code) <= 64),
  CHECK (
    (operation = 'upsert' AND document IS NOT NULL AND length(trim(document)) > 0 AND document_hash NOT GLOB '*[^0-9a-f]*' AND length(document_hash) = 64)
    OR
    (operation = 'delete' AND document IS NULL AND document_hash IS NULL)
  ),
  CHECK (
    (event_type IN ('memo.index.requested.v1', 'memo.reindex.requested.v1') AND operation = 'upsert')
    OR
    (event_type = 'memo.delete.requested.v1' AND operation = 'delete')
  )
);

CREATE INDEX idx_memo_index_outbox_status_id ON memo_index_outbox(status, id);
CREATE INDEX idx_memo_index_outbox_memo_sequence ON memo_index_outbox(memo_uid, source_sequence);
