# ilan-radari

Job-posting radar. Every 15 minutes a GitHub Actions run scans LinkedIn and Turkish job boards, filters postings against my profile, scores them with an LLM and sends the matches to Telegram with the CV I should apply with.

```
GitHub Actions (cron, 15 min)
  ├─ sources/      LinkedIn guest API · Kariyer.net · Eleman.net · isbul.net · Youthall
  ├─ matching.py   location (Konya, Karaman, remote) · title/description rules → track + CV · warnings
  ├─ llm.py        Gemini (free tier), batch scoring; falls back to rule score on quota errors
  ├─ telegram.py   message + inline buttons (applied / later / irrelevant) + commands
  └─ state.py      seen postings, source health → `state` branch (bot commits)
```

- **No accounts used for scraping.** LinkedIn is read through its public guest endpoints; nothing logs in.
- **Polite by design:** each source has its own interval (`SOURCE_INTERVAL_MIN`), small page counts, randomized delays.
- **Self-monitoring:** a source failing 3 runs in a row triggers a Telegram alert; a recovery message follows.
- **Daily summary** at 21:00 (Europe/Istanbul).

## Setup

Repository secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | token from @BotFather |
| `TELEGRAM_CHAT_ID` | your numeric chat id (@userinfobot) |
| `GEMINI_API_KEY` | Google AI Studio key (optional; without it rule scores are used) |

Filters live in [`radar/config.py`](radar/config.py); the candidate profile used for LLM scoring is [`radar/profile.md`](radar/profile.md).

## Telegram commands

`/durum` status and source health · `/bugun` today's summary · `/kaydedilenler` saved postings · `/duraklat` / `/devam` pause or resume

## Development

```bash
pip install -r requirements.txt pytest
python -m pytest -q          # parsers are tested against real pages captured from Actions runners
python -m radar              # without Telegram secrets, matches are printed instead of sent
```
