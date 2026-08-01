# Discord Hybrid Bot - Scheduled Messenger

A Discord bot that sends messages using a user account token on a configurable schedule.

## Features

- ✅ Uses Bot Token to stay online 24/7
- ✅ Sends messages using User Account Token
- ✅ Configurable schedule (1-60 minutes)
- ✅ Auto-discovers channels
- ✅ Rate limit handling
- ✅ Persistent settings
- ✅ Runs on Railway

## Commands

| Command | Description |
|---------|-------------|
| `!set_token <token>` | Set user token |
| `!add_channel <id>` | Add channel |
| `!remove_channel <id>` | Remove channel |
| `!list_channels` | List channels |
| `!set_message <msg>` | Set message |
| `!set_interval <min>` | Set interval (1-60 min) |
| `!start` | Start sending |
| `!stop` | Stop sending |
| `!send_now` | Send one round |
| `!status` | Show status |
| `!clear` | Clear settings |
| `!help` | Show help |

## Deployment

1. Create Discord Bot
2. Set BOT_TOKEN environment variable
3. Deploy to Railway
4. Invite bot to server
5. Configure with commands

## Environment Variables

- `BOT_TOKEN` - Your Discord Bot Token