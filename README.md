# Word Chain Discord Bot

A Discord bot for playing word chain games with AI-powered word validation.

## Features

- 🎮 **Party-based Game System**: Create parties with 2-10 players
- 🤖 **AI Word Validation**: Uses OpenAI or Anthropic to validate words
- ⏱️ **Visual Turn Timers**: Countdown with emoji progress bar (🟢🟡🔴⚪)
- 💀 **Elimination on Timeout**: Players are only eliminated when time runs out
- 🎯 **Game Modes**: Normal (1 letter) and Hard (2 letters)
- 📊 **Statistics & Leaderboards**: Track wins, words played, streaks

## Game Rules

1. Players take turns submitting words
2. Each word must start with the last letter(s) of the previous word
   - **Normal Mode**: Last 1 letter
   - **Hard Mode**: Last 2 letters
3. Words must be valid dictionary words (validated by AI)
4. **No plural forms** allowed (e.g., "cats" ❌, "cat" ✅)
5. **Invalid words** only result in a warning - you can try again
6. **Timeout** = elimination from the game
7. When a player is eliminated, the word chain resets
8. Last player standing wins!

## Commands

| Command | Description |
|---------|-------------|
| `/wordchain create` | Create a new game party |
| `/wordchain join` | Join an existing party |
| `/wordchain leave` | Leave a party (before game starts) |
| `/wordchain forfeit` | Forfeit during an active game |
| `/wordchain cancel` | Cancel the party (creator only) |
| `/wordchain status` | View current game status |
| `/wordchain stats` | View your statistics |
| `/wordchain leaderboard` | View server leaderboard |
| `/wordchain rules` | Display game rules |
| `/wordchain check` | Check if a word is valid |

## Setup

### Prerequisites

- Python 3.10+
- Discord Bot Token
- OpenAI API Key or Anthropic API Key

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd word-chain-discord-bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file from the example:
```bash
cp .env.example .env
```

4. Edit `.env` and fill in your credentials:
```env
DISCORD_TOKEN=your_discord_bot_token_here
AI_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key_here
```

5. Run the bot:
```bash
python main.py
```

## Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `DISCORD_TOKEN` | Discord bot token | Required |
| `AI_PROVIDER` | AI provider ("openai" or "anthropic") | openai |
| `OPENAI_API_KEY` | OpenAI API key | Required if using OpenAI |
| `ANTHROPIC_API_KEY` | Anthropic API key | Required if using Anthropic |
| `AI_MODEL` | AI model to use | gpt-4o-mini |
| `DATABASE_URL` | SQLite database URL | sqlite+aiosqlite:///word_chain_bot.db |
| `DEFAULT_TIMER_SECONDS` | Default turn timer | 30 |
| `MIN_PLAYERS` | Minimum players to start | 2 |
| `MAX_PLAYERS` | Maximum players per game | 10 |
| `DEV_MODE` | Enable debug logging | false |

## Project Structure

```
word-chain-discord-bot/
├── main.py                 # Bot entry point
├── config.py               # Settings and constants
├── database.py             # Database connection
├── models/
│   ├── __init__.py
│   ├── db_models.py        # SQLAlchemy models
│   └── game.py             # Game state dataclass
├── services/
│   ├── __init__.py
│   ├── ai_validator.py     # AI word validation
│   └── game_manager.py     # Game lifecycle management
├── cogs/
│   ├── __init__.py
│   ├── game_commands.py    # Slash commands
│   └── word_handler.py     # Message handler for words
├── views/
│   ├── __init__.py
│   ├── party_setup.py      # Party creation UI
│   └── game_ui.py          # Game embeds
├── utils/
│   ├── __init__.py
│   └── timer.py            # Turn timer utility
├── requirements.txt
├── pyproject.toml
├── .env.example
└── README.md
```

## Database Schema

### Tables

- **game_sessions**: Game session metadata
- **game_participants**: Players in each session
- **session_words**: Words played in each session
- **word_cache**: AI validation cache
- **player_stats**: Player statistics

## Timer Display

The timer shows remaining time with an emoji progress bar:

- 🟢🟢🟢🟢🟢🟢🟢🟢🟢🟢 (>50% time remaining)
- 🟡🟡🟡🟡🟡🟡⚪⚪⚪⚪ (25-50% time remaining)
- 🔴🔴🔴⚪⚪⚪⚪⚪⚪⚪ (<25% time remaining)

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
