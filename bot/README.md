# Discord bot refactoring code

This directory is a review artifact based on:

- `records/2026-09-06-bot-codebase-audit.md`
- `records/2026-09-06-bot-refactor-draft.md`

This is a complete replacement candidate for the contents of
`/home/remaindere/codex-discord/bot`. It includes the Discord event pipeline,
Codex CLI and Mantle Direct API adapters, safe attachments, request-scoped Git
auditing, raw/history/session/cost storage, web search, and tests.

The production directory was not changed. Keep the production `.env` when
copying because no credentials are included here.

## Deployment

```bash
cd /home/remaindere/codex-discord
cp bot/.env /tmp/codex-discord.env
cp -a memory/records/2026-09-06-bot-refactor-code/. bot/
cp /tmp/codex-discord.env bot/.env
python -m pip install -r bot/requirements.txt
python bot/discord_bot.py
```

Stop the running bot service before replacing its files.

## Verification

```bash
cd records/2026-09-06-bot-refactor-code
python -m compileall -q bot tests
python -m pytest -q
```

The integration suite creates a disposable real Git repository and a
six-page PDF larger than 1 MB. It does not call live external services.
