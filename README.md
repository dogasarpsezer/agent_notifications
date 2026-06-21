# Agent Notifications

A terminal app (Python, standard library only) that gives each agent lifecycle
**action** its own **sound folder**, lets you pick a specific sound or **random**,
and generates a **skill folder** you hand to an agent. The agent reads the skill
and installs the Node.js sound-playback hooks itself — this app never edits
your settings.

- **Cross-platform playback** — Python 3.8+ and Node.js 14+ on Windows, macOS,
  and Linux.
- **No sound paths to type** — you drop files into per-action folders.
- **Random mode** — a different sound on every event.

---

## Table of contents

1. [Concepts](#concepts)
2. [Install / run](#install--run)
3. [Quick start (copy-paste)](#quick-start-copy-paste)
4. [The interactive menu, step by step](#the-interactive-menu-step-by-step)
5. [Command-line reference](#command-line-reference)
6. [What `generate` produces](#what-generate-produces)
7. [Handing the folder to an agent](#handing-the-folder-to-an-agent)
8. [Testing playback directly](#testing-playback-directly)
9. [Tests](#tests)
10. [FAQ / troubleshooting](#faq--troubleshooting)

---

## Concepts

| Term | Meaning |
|------|---------|
| **Action** | An agent lifecycle event you want a sound for. |
| **Hook event** | The Claude Code event the action maps to (`Stop`, `Notification`, `SessionStart`, …). |
| **Sound folder** | `<app-dir>/sounds/<action-id>/` — drop `.wav` / `.mp3` files here. |
| **Selection** | Per action: a **specific file**, **random**, or **none**. |
| **Skill folder** | The portable bundle `generate` creates for an agent to install hooks. |

Default actions (the action set is **extensible** — add your own):

| Action id | Label | Hook event | Fires when |
|-----------|-------|-----------|------------|
| `task-complete` | Task complete | `Stop` | the agent finishes responding |
| `question` | Agent asks a question | `Notification` | the agent needs your attention |
| `session-start` | Session start | `SessionStart` | a session begins |

---

## Install / run

No installation needed. From the project directory:

```bash
python agent_notifications.py            # interactive menu
python agent_notifications.py --help     # CLI help
```

On first run the app creates a sound folder for every action under `sounds/`.

---

## Quick start (copy-paste)

This is the fastest path: see your folders, drop in sounds, choose them, generate.

```bash
# 1. See where to put sounds (folders are auto-created)
python agent_notifications.py folders
```
```text
task-complete: C:\Users\PC\Desktop\AgentNotifications\sounds\task-complete
    (empty - drop .wav/.mp3 files here)
question: C:\Users\PC\Desktop\AgentNotifications\sounds\question
    (empty - drop .wav/.mp3 files here)
session-start: C:\Users\PC\Desktop\AgentNotifications\sounds\session-start
    (empty - drop .wav/.mp3 files here)
```

```bash
# 2. Drop sound files into the folders (any .wav / .mp3). Example with Windows sounds:
cp /c/Windows/Media/chimes.wav  sounds/task-complete/
cp /c/Windows/Media/ding.wav    sounds/task-complete/
cp /c/Windows/Media/notify.wav  sounds/task-complete/
cp "/c/Windows/Media/Windows Logon.wav" sounds/session-start/

# 3. Confirm they're there
python agent_notifications.py folders
```
```text
task-complete: C:\Users\PC\Desktop\AgentNotifications\sounds\task-complete
    - chimes.wav
    - ding.wav
    - notify.wav
question: C:\Users\PC\Desktop\AgentNotifications\sounds\question
    (empty - drop .wav/.mp3 files here)
session-start: C:\Users\PC\Desktop\AgentNotifications\sounds\session-start
    - Windows Logon.wav
```

```bash
# 4. Choose a sound per action — random for one, a specific file for another
python agent_notifications.py set task-complete --random
python agent_notifications.py set session-start --file "Windows Logon.wav"
```
```text
+ 'task-complete' -> random (sounds/task-complete)
+ 'session-start' -> sounds/session-start/Windows Logon.wav
```

```bash
# 5. (optional) Add a custom action — this also creates its folder
python agent_notifications.py add --id subagent-done --label "Subagent done" --event SubagentStop
```
```text
+ Added 'subagent-done'. Folder: C:\Users\PC\Desktop\AgentNotifications\sounds\subagent-done
```

```bash
# 6. Review, then generate the skill folder
python agent_notifications.py list
```
```text
Actions:
  1. Task complete            [Stop]  sound: random (sounds/task-complete)
  2. Agent asks a question    [Notification]  sound: (not set)
  3. Session start            [SessionStart]  sound: sounds/session-start/Windows Logon.wav
  4. Subagent done            [SubagentStop]  sound: (not set)
```

```bash
python agent_notifications.py generate
```
```text
+ Skill folder generated at: C:\Users\PC\Desktop\AgentNotifications\agent-notifications-skill
```

You now have an `agent-notifications-skill/` folder ready to hand to an agent.

---

## The interactive menu, step by step

Launch with no arguments:

```bash
python agent_notifications.py
```
```text
================================================================
 Agent Notifications - sound notifications for agent events
================================================================
 Sound folders live under: C:\Users\PC\Desktop\AgentNotifications\sounds

Actions:
  1. Task complete            [Stop]  sound: (not set)
  2. Agent asks a question    [Notification]  sound: (not set)
  3. Session start            [SessionStart]  sound: (not set)

Menu:  [#] choose sound   a add   d delete   g generate skill
       i generate&implement (install to global skills)   s save   q quit
>
```

**Choose a sound for an action** — type its number. The app lists the files in
that action's folder with sizes, plus `r` (random) and `n` (none):

```text
> 1

--- Sound for 'Task complete' ---
Folder: C:\Users\PC\Desktop\AgentNotifications\sounds\task-complete
Current selection: (not set)

Available sounds:
  1. chimes.wav  (28 KB)
  2. ding.wav  (12 KB)
  3. notify.wav  (78 KB)

  r. Random  - play a random sound from this folder each time
  n. None    - disable this action
Choose [#/r/n] (blank to keep): r
+ 'Task complete' set to RANDOM (3 sound(s)).
```

> If the folder is empty it tells you the path to drop files into, then you
> pick the action again to choose.

**Add a custom action** — `a`, then answer the prompts; the app creates the
folder and immediately lets you choose a sound:

```text
> a

New action label (e.g. 'Subagent done'): Subagent done
Action id (kebab-case, blank = auto): subagent-done

Hook event:
  1. Stop
  2. Notification
  3. SessionStart
  4. SubagentStop
  ...
Choose event number: 4
+ Added 'Subagent done' [SubagentStop]. Created folder:
    C:\Users\PC\Desktop\AgentNotifications\sounds\subagent-done
  Drop .wav/.mp3 files there, then pick a sound for it.
```

**Generate & implement** — type `i` to generate the skill *and* install it
straight into your global skills folder (`~/.claude/skills/agent-notifications`),
overwriting any previous install:

```text
> i

Overwriting existing skill at:
    C:\Users\PC\.claude\skills\agent-notifications

+ Skill generated and installed to the global skills folder:
    C:\Users\PC\.claude\skills\agent-notifications
  Restart/reload Claude Code, then ask your agent to enable notifications.
```

This makes the `agent-notifications` skill available in every Claude Code
session — no need to hand the folder over manually. `g` (generate to a local
folder) still works if you'd rather move it yourself.

**Other keys:** `d` delete an action · `g` generate the skill folder · `i`
generate & install to global skills · `s` save the config · `q` quit (offers to
save first).

---

## Command-line reference

Every interactive action has a scriptable equivalent. Global flag: `--config <path>`
to use an alternate `notifications.json`.

| Command | Description |
|---------|-------------|
| `list` | List actions and their current selection. |
| `folders` | Print each action's folder and the files in it. |
| `set <id> --random` | Play a random file from the action's folder each time. |
| `set <id> --file <name>` | Use a specific file (must already be in the folder). |
| `set <id> --none` | Disable the action. |
| `add --id <id> --label <text> --event <Event> [--matcher <m>]` | Add a custom action and create its folder. |
| `remove <id>` | Remove an action (its folder is left on disk). |
| `generate [--output <dir>]` | Build the skill folder (default `./agent-notifications-skill`). |
| `implement [--skills-dir <dir>]` | Build the skill and install it into the global skills folder (default `~/.claude/skills/agent-notifications`), overwriting any existing install. |

```bash
# Examples
python agent_notifications.py set question --file ask.mp3
python agent_notifications.py set task-complete --none
python agent_notifications.py add --id pre-bash --label "Before Bash" --event PreToolUse --matcher Bash
python agent_notifications.py generate --output C:\Users\PC\my-skill

# Generate and install into ~/.claude/skills/agent-notifications in one step
python agent_notifications.py implement
```
```text
+ Skill installed to global skills folder: C:\Users\PC\.claude\skills\agent-notifications
```

**Hook events available:** `Stop`, `Notification`, `SessionStart`, `SubagentStop`,
`UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PreCompact`, `SessionEnd`.
`PreToolUse` / `PostToolUse` accept a `--matcher` (e.g. `Bash`, `*`).

---

## What `generate` produces

```text
agent-notifications-skill/
├── SKILL.md            # instructions the agent follows to install the hooks
├── notifications.json  # the action -> event -> selection mapping
├── play_sound.js       # plays --path <file>, or --folder <dir> --random
└── sounds/
    ├── task-complete/  # all files (random copies the whole folder)
    │   ├── chimes.wav
    │   ├── ding.wav
    │   └── notify.wav
    └── session-start/
        └── Windows Logon.wav   # single selection copies only the chosen file
```

`SKILL.md` embeds a ready-to-merge `hooks` block (with a `<SKILL_DIR>` placeholder
the agent replaces with the real absolute path):

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node \"<SKILL_DIR>/play_sound.js\" --folder \"<SKILL_DIR>/sounds/task-complete\" --random"
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node \"<SKILL_DIR>/play_sound.js\" --path \"<SKILL_DIR>/sounds/session-start/Windows Logon.wav\""
          }
        ]
      }
    ]
  }
}
```

A **random** action becomes `--folder ... --random` (Node.js re-picks on every
event); a **single** action becomes `--path ...`.

---

## Handing the folder to an agent

1. Give the generated `agent-notifications-skill/` folder to your agent — in
   Claude Code, add it as a skill or point Claude at the directory.
2. Ask it to **enable notification sounds**. It merges the `hooks` block from
   `SKILL.md` into `.claude/settings.json`, substituting the folder's real path.
3. Restart / reload the agent so the hooks take effect.
4. To turn sounds off, ask it to **disable notifications** — it removes the hook
   entries that reference this folder's `play_sound.js`.

---

## Testing playback directly

You don't need an agent to hear a sound. Run `play_sound.js` yourself:

```bash
# A random file from a folder
node "./agent-notifications-skill/play_sound.js" \
  --folder "./agent-notifications-skill/sounds/task-complete" --random

# A specific file
node "./agent-notifications-skill/play_sound.js" \
  --path "./agent-notifications-skill/sounds/session-start/Windows Logon.wav"
```

Playback uses `afplay` on macOS, the registered media application on Windows,
and the first available supported player on Linux (`paplay`, `aplay`, `ffplay`,
`mpv`, or `play`). Keep notification clips short because the hook waits.

---

## Tests

```bash
python -m unittest test_agent_notifications -v
```

The app and tests are pure Python; Node.js is used for actual sound playback.

---

## FAQ / troubleshooting

**The folder for an action is empty when I generate.**
A random action needs at least one file and a single action needs its chosen file
present, or `generate` errors. Drop files into the folder first.

**Nothing plays when the hook fires.**
Test with `play_sound.js` directly (above). Check the file exists, the path in
`settings.json` is absolute, and `node` is available on `PATH`. On Linux, ensure
one of the supported audio player commands is installed.

**I deleted an action but its folder is still there.**
Intentional — your sound files are left on disk. Delete the folder manually if you
want it gone.

**Can I use MP3?**
Yes. WAV and MP3 are supported when the platform's selected player supports them.

**Where do sounds live when packaged as an `.exe`?**
Next to the executable: `<exe-dir>/sounds/<action-id>/`.
