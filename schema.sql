CREATE TABLE IF NOT EXISTS comparison_history (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    old_path TEXT NOT NULL,
    new_path TEXT NOT NULL,
    added_count INTEGER NOT NULL CHECK (added_count >= 0),
    changed_count INTEGER NOT NULL CHECK (changed_count >= 0),
    deleted_count INTEGER NOT NULL CHECK (deleted_count >= 0),
    unchanged_count INTEGER NOT NULL CHECK (unchanged_count >= 0),
    compared_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
