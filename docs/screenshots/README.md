# Screenshots and demo GIF

This directory is reserved for human-captured demo media.

- `demo.gif` — the 15-second walkthrough used at the top of the README and linked
  from `docs/architecture.md`. Record it from the real UI (the demo stack with
  the mock model), not from mock-ups:
  1. open `/`, send a message → tokens stream in;
  2. ask `Can you guarantee a refund?` → the reply becomes the safe fallback;
  3. open `/admin`, take over → send another message from `/` and the AI stays
     silent; release and it answers again.
- Optional stills: `chat.png`, `flow.png`, `support.png`, captured from the same
  session.

Suggested recording command (Windows, Edge or Chrome, via Playwright):

```bash
npx playwright codegen http://localhost
```

Keep the file size reasonable (≤ 3 MB) and commit only media you captured
yourself. The agent that built this repository captured verification stills
outside the repository, in its own evidence folder; those are not committed.
