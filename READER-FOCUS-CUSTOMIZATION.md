# Reader focus customization

Before reading starts, a writer may lightly customize each selected reader:

- one primary focus from 19 curated choices;
- up to two distinct secondary interests;
- one optional natural-language attention note, limited to 160 characters;
- removal of generated personal tastes that feel exaggerated or unsuitable.

Generated `+ / −` tastes remain part of the reader's identity. They are soft preferences, not assignments or predicted verdicts. Writers cannot add or rewrite them; they can only dismiss them or regenerate the reader.

The active prompt labels personal tastes, assigned focus, and the writer note separately. Every layer explicitly says that it may affect attention but cannot force an opinion or require a comment.

When `/read-all` passes its cost preflight, the manuscript's `reader_config_locked` flag is set permanently. The backend then rejects focus edits, reader regeneration, and additions with HTTP 409 even if a client bypasses the UI.

Schema migration: `backend/migrations/005_reader_focus_customization.sql`.
