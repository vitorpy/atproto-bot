# ATproto Bot with LLM Integration

A Bluesky/ATproto bot that responds to mentions with LLM-generated responses, using thread context for intelligent replies.

## Features

- **Single-owner mode**: Only responds to mentions from a configured owner DID
- **Thread context**: Fetches full thread context when mentioned
- **LLM integration**: Uses LangChain with Anthropic (Claude) or OpenAI
- **Prompt injection mitigation**: Strong separation between context and instructions
- **Rate limiting**: Configurable per-user rate limits
- **Graceful error handling**: Continues operation despite individual failures

## Security: Prompt Injection Mitigation

This bot implements multiple layers of protection against prompt injection:

1. **Structural separation**: Thread context and user instructions are wrapped in clearly labeled XML tags (`<THREAD_CONTEXT>` and `<USER_INSTRUCTION>`)

2. **System prompt hardening**: The system prompt explicitly instructs the LLM to:
   - Treat THREAD_CONTEXT as untrusted data only
   - Ignore any instructions found within the context
   - Only follow commands from USER_INSTRUCTION
   - Recognize common injection patterns

3. **Input sanitization**: Basic sanitization removes control characters and Unicode tricks

4. **Owner-only responses**: Only responds to the configured owner DID, preventing abuse from arbitrary users

## Installation

### Prerequisites

- Python 3.11+
- A Bluesky account for the bot
- An Anthropic or OpenAI API key

### Setup

#### Option 1: Using uv (Recommended)

[uv](https://github.com/astral-sh/uv) is a fast Python package manager that simplifies dependency management.

```fish
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone or copy the project
cd atproto-bot

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate.fish

# Install the project
uv pip install -e .

# For development
uv pip install -e ".[dev]"
```

#### Option 2: Using pip

```fish
# Clone or copy the project
cd atproto-bot

# Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate.fish

# Install dependencies
pip install -e .

# For development
pip install -e ".[dev]"
```

## Configuration

1. Copy the example config:

```fish
cp config.example.yaml config.yaml
```

2. Edit `config.yaml` with your values:

```yaml
bluesky:
  handle: "your-bot.bsky.social"
  app_password: "xxxx-xxxx-xxxx-xxxx"  # Create at Settings > App Passwords
  owner_did: "did:plc:your-did-here"

llm:
  provider: "anthropic"  # or "openai"
  api_key: "sk-ant-xxxxx"
  model: "claude-sonnet-4-20250514"
  max_tokens: 1024
  temperature: 0.7

bot:
  poll_interval: 30
  max_thread_depth: 50
  rate_limit_per_hour: 20
  max_post_length: 300
```

### Finding Your DID

To find your Bluesky DID:

```fish
curl "https://bsky.social/xrpc/com.atproto.identity.resolveHandle?handle=yourhandle.bsky.social"
```

### Creating an App Password

1. Go to Bluesky Settings
2. Navigate to "App Passwords"
3. Create a new app password for the bot
4. **Never use your main password**

## Usage

### Run the bot

```fish
# With default config.yaml
python -m src.main

# Or use the installed command
atproto-bot

# With uv (if you installed with uv)
uv run python -m src.main
# or
uv run atproto-bot

# With custom config
atproto-bot -c /path/to/config.yaml

# Verbose logging
atproto-bot -v

# Single poll cycle (for testing)
atproto-bot --once
```

### Interacting with the bot

1. Create a post or reply in a thread
2. Mention the bot: `@your-bot.bsky.social summarize this discussion`
3. The bot will fetch the thread context and respond

### Example interactions

```
You: @mybot.bsky.social what are the main points here?
Bot: The thread discusses three main topics: [summary based on context]

You: @mybot.bsky.social translate the above to Spanish
Bot: [Spanish translation of the relevant context]

You: @mybot.bsky.social who seems to be winning this argument?
Bot: [Analysis of the debate based on thread context]
```

## Self-Improvement Feature

The bot can autonomously improve its own codebase using the `/selfimprovement` slash command.

### Overview

When you send `/selfimprovement [PROMPT]`, the bot will:
1. Analyze the codebase using Claude
2. Generate code changes based on your prompt
3. Create a new Git branch
4. Commit the changes
5. Push to GitHub
6. Create a pull request
7. Reply with the PR link

**Example:**
```
You: @mybot /selfimprovement Add better error handling to mention processing
Bot: Starting self-improvement process... This may take a few minutes. I'll reply when done.
Bot: ✅ Self-improvement complete!
     Pull request created: https://github.com/vitorpy/atproto-bot/pull/42
     Review and merge when ready.
```

### GitHub App Setup (Required for /selfimprovement)

The self-improvement feature requires a GitHub App for authentication.

#### 1. Create GitHub App

1. Go to GitHub Settings → Developer settings → [GitHub Apps](https://github.com/settings/apps) → **New GitHub App**
2. Fill in the details:
   - **App name:** `atproto-bot-selfimprovement` (or any unique name)
   - **Homepage URL:** `https://github.com/vitorpy/atproto-bot`
   - **Webhook:** Uncheck "Active" (not needed)
3. Set **Repository permissions:**
   - **Contents:** Read & Write
   - **Pull Requests:** Read & Write
4. **Where can this GitHub App be installed?** → "Only on this account"
5. Click **Create GitHub App**

#### 2. Configure GitHub App

After creation:

1. **Generate Private Key:**
   - Scroll down to "Private keys"
   - Click "Generate a private key"
   - Download the `.pem` file (keep it secure!)

2. **Note the App ID:**
   - At the top of the page, note your **App ID**

3. **Install the App:**
   - Click "Install App" in the left sidebar
   - Select your account
   - Choose "Only select repositories"
   - Select `vitorpy/atproto-bot`
   - Click "Install"

4. **Get Installation ID:**
   - After installation, you'll be redirected to a URL like:
     `https://github.com/settings/installations/12345678`
   - The number at the end (`12345678`) is your **Installation ID**

#### 3. Add GitHub Config

Add the GitHub section to your `config.yaml`:

```yaml
bluesky:
  handle: "your-bot.bsky.social"
  app_password: "xxxx-xxxx-xxxx-xxxx"
  owner_did: "did:plc:your-did-here"

llm:
  provider: "anthropic"
  api_key: "sk-ant-xxxxx"
  model: "claude-sonnet-4-20250514"
  max_tokens: 1024
  temperature: 0.7

bot:
  poll_interval: 30
  max_thread_depth: 50
  rate_limit_per_hour: 20
  max_post_length: 300

# GitHub App configuration (optional - required for /selfimprovement)
github:
  app_id: "123456"
  private_key: "${GITHUB_APP_PRIVATE_KEY}"  # Environment variable
  installation_id: "78910"
  repository: "vitorpy/atproto-bot"
```

#### 4. Set Environment Variable

Store the private key as an environment variable:

```bash
# On VPS (production)
export GITHUB_APP_PRIVATE_KEY=$(cat /path/to/private-key.pem)

# Or add to systemd service file
Environment="GITHUB_APP_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----"
```

For GitHub Actions deployment, add these secrets to your repository:
- `GITHUB_APP_ID`
- `GITHUB_APP_PRIVATE_KEY` (entire PEM content)
- `GITHUB_APP_INSTALLATION_ID`

### Usage Examples

```
# Simple feature addition
@bot /selfimprovement Add logging to all database operations

# Refactoring
@bot /selfimprovement Refactor config loading to use environment variables

# Bug fixes
@bot /selfimprovement Fix the rate limiting logic to reset properly

# Testing
@bot /selfimprovement Add unit tests for the command router
```

### How It Works

1. **Authorization:** Only the bot owner (configured `owner_did`) can use this command
2. **Code Analysis:** Claude reads the codebase structure and key files
3. **Change Generation:** Claude generates minimal, focused changes following existing patterns
4. **Validation:** Changes are validated for Python syntax and security
5. **Git Workflow:** Creates a feature branch, commits, and pushes to GitHub
6. **Pull Request:** Creates a PR with detailed description
7. **Manual Review:** You review and merge the PR (no auto-merge for safety)

### Safety Features

- **Owner-only:** Only you can trigger self-improvement
- **No auto-merge:** All changes require manual PR review
- **Validation:** Code is checked for syntax errors before commit
- **Audit trail:** All changes are tracked in Git history
- **Rollback:** Easy to revert via Git if needed

### VPS Setup Notes

If running on a VPS, ensure:

```bash
# Git is configured
git config --global user.name "ATproto Bot"
git config --global user.email "bot@vitorpy.com"

# Repository is in expected location
cd /var/www/atproto-bot
git status  # Should show clean working directory
```

## Architecture

```
src/
├── main.py          # Entry point and CLI
├── config.py        # Configuration loading and validation
├── atproto_client.py # Bluesky API interactions
├── llm_handler.py   # LangChain integration with injection mitigation
└── bot.py           # Main bot logic and orchestration
```

### Components

- **Config**: Pydantic-based configuration with validation
- **ATProtoClient**: Wraps the atproto library for notifications, threads, and posting
- **LLMHandler**: LangChain integration with structured prompts
- **Bot**: Orchestrates polling, processing, and rate limiting

## Deployment

The bot is deployed to scherbius.vitorpy.com as a systemd service.

### Automatic Deployment

Deployments happen automatically when code is pushed to the `main` branch:

1. Push to main
2. GitHub Actions builds and deploys
3. Service restarts with new code

### Manual Deployment

To manually trigger deployment:

1. Go to GitHub Actions
2. Select "Deploy ATproto Bot to VPS" workflow
3. Click "Run workflow"

### Viewing Logs

On scherbius.vitorpy.com:

```bash
# Follow logs in real-time
sudo journalctl -u atproto-bot -f

# View recent logs
sudo journalctl -u atproto-bot -n 100

# View logs since last boot
sudo journalctl -u atproto-bot -b
```

### Service Management

```bash
# Check service status
sudo systemctl status atproto-bot

# Restart service
sudo systemctl restart atproto-bot

# Stop service
sudo systemctl stop atproto-bot

# Start service
sudo systemctl start atproto-bot
```

### Database Location

The SQLite database is stored at: `/var/lib/atproto-bot/bot.db`

### Troubleshooting Deployment

**Service won't start:**
```bash
# Check logs for errors
sudo journalctl -u atproto-bot -n 50

# Verify config file exists
ls -l /var/www/atproto-bot/config.yaml

# Check database permissions
ls -ld /var/lib/atproto-bot
```

**Database issues:**
```bash
# Verify database exists
ls -lh /var/lib/atproto-bot/bot.db

# Check database structure
sqlite3 /var/lib/atproto-bot/bot.db ".tables"
```

## Running as a Service (Generic)

For other environments, you can run the bot as a service using systemd or Docker.

### systemd (Linux)

Create `/etc/systemd/system/atproto-bot.service`:

```ini
[Unit]
Description=ATproto Bot
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/atproto-bot
ExecStart=/path/to/atproto-bot/.venv/bin/python -m src.main
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

```fish
sudo systemctl daemon-reload
sudo systemctl enable atproto-bot
sudo systemctl start atproto-bot
```

### Docker

#### Using pip

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e .

CMD ["python", "-m", "src.main"]
```

#### Using uv (faster builds)

```dockerfile
FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY . .

# Install dependencies with uv
RUN uv venv && \
    . .venv/bin/activate && \
    uv pip install -e .

CMD [".venv/bin/python", "-m", "src.main"]
```

```fish
docker build -t atproto-bot .
docker run -v (pwd)/config.yaml:/app/config.yaml atproto-bot
```

## Development

### With uv

```fish
# Install dev dependencies
uv pip install -e ".[dev]"

# Run linter
uv run ruff check src/

# Run formatter
uv run ruff format src/

# Run tests
uv run pytest
```

### With pip

```fish
# Install dev dependencies
pip install -e ".[dev]"

# Run linter
ruff check src/

# Run formatter
ruff format src/

# Run tests
pytest
```

## Troubleshooting

### "Rate limit exceeded"

The bot limits responses per user per hour. Adjust `rate_limit_per_hour` in config.

### "Post not found"

The thread may have been deleted or the post is from a blocked account.

### "Config file not found"

Ensure `config.yaml` exists in the working directory or specify path with `-c`.

### Authentication errors

- Verify your app password is correct
- Ensure the handle matches your Bluesky account
- Check that the app password hasn't been revoked

## License

MIT
