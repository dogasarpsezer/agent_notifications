---
name: agent-notifications
description: >-
  Play sound notifications for agent lifecycle events. When this skill folder is
  available and the user asks to enable (or disable) notification sounds, create
  (or remove) Claude Code hooks that play a sound for each action via PowerShell.
  Each action has its own folder under sounds/<action-id>; a "random" action plays
  a random file from its folder each time. Covers task complete (Stop), question
  asked (Notification), session start (SessionStart), and any custom actions below.
---

# Agent Notifications

This skill maps agent lifecycle **actions** to **sound folders** and tells you how
to wire them up as Claude Code hooks that play through PowerShell on Windows.

Each action owns a folder `sounds/<action-id>/` next to this file. An action is
either set to a **specific file** in its folder or to **random** (PowerShell picks
a different file from the folder on every play). The configurator that produced
this folder does **not** edit settings itself - installing the hooks is your job,
performed only when the user asks.

## Action -> hook event -> sound source

| Action | Hook event | Sound source |
|--------|-----------|--------------|
| Task complete | `Stop` | `sounds/task-complete/Complete Sound effect ( No copyright ).mp3` |
| Agent asks a question | `Notification` | `sounds/question/Question.mp3` |
| Session start | `SessionStart` | `sounds/session-start/J.A.R.V.I.S 4K UHD LIVE WALLPAPER - WELCOME BACK SIR.mp3` |

Actions with no sound source are skipped. For a "random" action, look in its
`sounds/<action-id>/` folder at play time and pick any `.wav`/`.mp3`.

## How to install the hooks

Do this when the user asks you to enable notification sounds.

1. Determine the absolute path of **this** skill folder (the directory that
   contains this `SKILL.md`). Call it `SKILL_DIR`.
2. Choose the settings file: default to the project's `.claude/settings.json`
   (create it if missing). Use the user file `~/.claude/settings.json` only if
   the user asks for notifications everywhere.
3. Merge the `hooks` block below into that settings file. **Replace every
   `<SKILL_DIR>`** with the real absolute path from step 1 (use doubled
   backslashes inside JSON, e.g. `C:\\Users\\me\\agent-notifications-skill`).
   If a hook event already exists in the file, **append** to its array instead of
   overwriting it.
4. Confirm the merged JSON is valid, then tell the user to restart or reload
   Claude Code so the hooks take effect.

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "powershell -NoProfile -ExecutionPolicy Bypass -File \"<SKILL_DIR>\\play_sound.ps1\" -Path \"<SKILL_DIR>\\sounds\\task-complete\\Complete Sound effect ( No copyright ).mp3\""
          }
        ]
      }
    ],
    "Notification": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "powershell -NoProfile -ExecutionPolicy Bypass -File \"<SKILL_DIR>\\play_sound.ps1\" -Path \"<SKILL_DIR>\\sounds\\question\\Question.mp3\""
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "powershell -NoProfile -ExecutionPolicy Bypass -File \"<SKILL_DIR>\\play_sound.ps1\" -Path \"<SKILL_DIR>\\sounds\\session-start\\J.A.R.V.I.S 4K UHD LIVE WALLPAPER - WELCOME BACK SIR.mp3\""
          }
        ]
      }
    ]
  }
}
```

`play_sound.ps1` resolves the sound: `-Path <file>` plays that file; `-Folder <dir>
-Random` plays a random `.wav`/`.mp3` from the folder on each invocation.

## Removing the hooks

To disable notifications, remove the hook entries whose `command` references this
skill folder's `play_sound.ps1` from the settings file, leaving any unrelated
hooks intact.

## Testing playback manually

```
powershell -NoProfile -ExecutionPolicy Bypass -File "<SKILL_DIR>\play_sound.ps1" -Folder "<SKILL_DIR>\sounds\task-complete" -Random
```

## Notes

- `play_sound.ps1` plays `.wav` synchronously (System.Media.SoundPlayer) and
  `.mp3`/other formats via System.Windows.Media.MediaPlayer.
- The hook waits for playback to finish; mp3 playback is capped at `-MaxSeconds`
  (default 15). Keep notification clips short.
- Available hook events: `Stop`, `Notification`, `SessionStart`, `SubagentStop`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PreCompact`, `SessionEnd`.
