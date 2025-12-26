# Word Chain Discord Bot

A Discord bot for playing word-chain with party lobbies, visual timers, and stats tracking. Words are validated using the Free Dictionary API (no API key required).

## Features

- 🎮 **Party system**: Create and join parties (2–10 players)
- ⏱️ **Visual turn timers**: Emoji progress (🟢🟡🔴⚪)
- 💀 **Timeout elimination**: Only timeouts eliminate players
- 🎯 **Modes**: Normal (1 last letter) and Hard (2 last letters)
- 📊 **Stats & leaderboard**: Games played/won, words, streaks

## Quick Start

1) Create a Discord application + bot in the Discord Developer Portal, invite it to your server with scopes `bot` and `applications.commands`. Enable the “Message Content Intent”.

2) Clone and install dependencies

```bash
git clone https://github.com/Rowlec/DISCORD-LINKING-WORD-BOT.git
cd DISCORD-LINKING-WORD-BOT
python -m pip install -r requirements.txt
```

3) Create your environment file

- Windows (PowerShell):

```powershell
Copy-Item .env.example .env
```

- macOS/Linux:

```bash
cp .env.example .env
```

4) Edit `.env` and set at least:

```dotenv
DISCORD_TOKEN=your_discord_bot_token
```

You can also adjust other settings like `DEFAULT_TIMER_SECONDS`, `MIN_PLAYERS`, `MAX_PLAYERS`, or `DATABASE_URL`.

5) Run the bot

```bash
python main.py
```

Slash commands will auto-sync the first time the bot starts.

## Commands

| Command | Description |
|---|---|
| `/wordchain create` | Create a new party with mode/timer options |
| `/wordchain join` | Join the party in the current channel |
| `/wordchain leave` | Leave before the game starts |
| `/wordchain forfeit` | Forfeit during an active game |
| `/wordchain cancel` | Cancel the party (creator only) |
| `/wordchain status` | Current game status (mode, timer, players) |
| `/wordchain stats` | Your statistics (or for another user) |
| `/wordchain leaderboard` | Server leaderboard with sorting |
| `/wordchain rules` | Game rules overview |
| `/wordchain check` | Validate a word quickly |

## Game Rules

1. Take turns submitting words.
2. Each word must start with the last letter(s) of the previous word:
   - Normal: last 1 letter
   - Hard: last 2 letters
3. Words must be valid dictionary words.
4. No plural forms (e.g., "cats" ❌, "cat" ✅).
5. Invalid words only warn you — try again.
6. Timeout eliminates the player.
7. When someone is eliminated, the chain resets.
8. Last player standing wins.

## Configuration

Environment variables loaded from [.env](.env.example):

| Variable | Description | Default |
|---|---|---|
| `DISCORD_TOKEN` | Discord bot token | — |
| `DATABASE_URL` | Database URL | `sqlite+aiosqlite:///word_chain_bot.db` |
| `DEFAULT_TIMER_SECONDS` | Turn timer seconds | `30` |
| `MIN_PLAYERS` | Minimum players to start | `2` |
| `MAX_PLAYERS` | Maximum players in party | `10` |
| `TIMER_UPDATE_INTERVAL` | Embed update interval (s) | `3` |
| `WORD_CACHE_EXPIRY_DAYS` | Cache TTL for validations | `30` |
| `DEV_MODE` | Extra debug logging | `false` |

Notes:
- Word validation uses the Free Dictionary API and does not require API keys.
- Any `AI_PROVIDER`/`OPENAI_`/`ANTHROPIC_` variables in the example file are currently unused.

## Project Structure

```
DISCORD-LINKING-WORD-BOT/
├── main.py                 # Entry point (logging, startup, sync commands)
├── config.py               # Env-backed settings and constants
├── database.py             # Async SQLAlchemy session + setup
├── models/
│   ├── db_models.py        # SQLAlchemy models (sessions, participants, cache, stats)
│   └── game.py             # In-memory game state and player info
├── services/
│   ├── game_manager.py     # Game lifecycle, DB persistence
│   └── word_validator.py   # Free Dictionary API validator + caching
├── cogs/
│   ├── game_commands.py    # Slash commands group `/wordchain`
│   └── word_handler.py     # In-channel word handling + timer integration
├── views/
│   ├── party_setup.py      # Party creation/join UI
│   └── game_ui.py          # Embeds for game states
├── utils/timer.py          # Timer manager for turns
├── .env.example            # Env template (copy to .env)
└── requirements.txt
```

## Security & Secrets

- Do not commit `.env`. It is ignored by [.gitignore](.gitignore).
- If a token was ever committed, rotate it in the Discord portal and update your local `.env`.
- GitHub Push Protection may block pushes that include secrets; follow its guidance to resolve.

## Troubleshooting

- Bot won’t start: ensure `DISCORD_TOKEN` is set and valid (see logs in [logs/bot.log](logs/bot.log)).
- Slash commands missing: invite with `applications.commands` scope; wait up to a minute for sync.
- Word validation errors: temporary Dictionary API issues will mark words invalid; try again later.
- Message content not received: enable “Message Content Intent” in the bot settings and ensure the bot has permissions to read messages and history.

## License

MIT

## Contributing

PRs welcome. Please avoid committing secrets and run formatting/linting if you use the optional dev toolchain in [pyproject.toml](pyproject.toml).
