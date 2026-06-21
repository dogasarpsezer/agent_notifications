# Agent Notifications

A TypeScript CLI that configures sound notifications for agent lifecycle events
and generates a portable agent skill. Each action has its own sound folder and
can use one specific file, a random file, or no sound.

## Requirements

- Node.js 18 or newer
- npm

## Install and run

```bash
npm install
npm start
```

`npm start` opens the interactive menu. During development you can also build
once and invoke the compiled CLI directly:

```bash
npm run build
node dist/cli.js --help
node dist/cli.js list
```

After publishing or installing the package globally, the binary is available as:

```bash
agent-notifications list
```

The app reads `AgentNotifications/notifications.json` and stores source sounds in
`AgentNotifications/sounds/<action-id>/`.

## Typical workflow

```bash
# Show each action's sound directory
node dist/cli.js folders

# Select a random or specific sound
node dist/cli.js set task-complete --random
node dist/cli.js set question --file "Question.mp3"

# Add a custom action
node dist/cli.js add --id subagent-done --label "Subagent done" --event SubagentStop

# Generate the portable skill
node dist/cli.js generate

# Or install it into ~/.claude/skills/agent-notifications
node dist/cli.js implement
```

## Commands

| Command | Description |
|---|---|
| `list` | List actions and selections. |
| `folders` | Show sound folders and their audio files. |
| `set <id> --random` | Pick a random sound for every event. |
| `set <id> --file <name>` | Select one file from the action folder. |
| `set <id> --none` | Disable an action. |
| `add --id <id> --label <label> --event <event>` | Add an action. |
| `remove <id>` | Remove an action without deleting its sounds. |
| `generate [--output <dir>]` | Generate a portable skill folder. |
| `implement [--skills-dir <dir>]` | Install the generated skill globally. |

Use `--config <path>` before the command to use another configuration file.
Supported audio formats are `.wav` and `.mp3`.

## Development

```bash
npm run build
npm test
```

Source lives in `src/`; compiled output is written to `dist/`. Tests use Node's
built-in test runner and require no audio player.

## Generated skill

The default output is `AgentNotifications/agent-notifications-skill/` and contains:

```text
SKILL.md
notifications.json
package.json
play_sound.js
sounds/<action-id>/...
```

The generated `play_sound.js` is a self-contained Node.js hook runtime. It uses
`afplay` on macOS, Windows' built-in MCI audio API through a hidden process, and
`paplay`, `aplay`, `ffplay`, `mpv`, or `play` on Linux. Playback does not open a
media-player window.

## License

MIT
