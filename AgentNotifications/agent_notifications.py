#!/usr/bin/env python3
"""Agent Notifications - terminal configurator.

An interactive terminal application that gives each agent lifecycle *action*
(task complete, agent asks a question, session start, plus any custom actions)
its own **sound folder** inside the application's directory. You drop one or more
`.wav` / `.mp3` files into an action's folder, then choose - per action - either a
specific file or **random** (a different sound each time it fires).

It does NOT touch your Claude Code settings. Instead it *generates a skill
folder* containing:

  * SKILL.md          - instructions an agent reads to create the hooks itself
  * notifications.json - the action -> hook-event -> sound mapping
  * play_sound.js     - cross-platform Node.js sound playback
  * sounds/<action>/  - copies of each action's sound files (portable)

When you hand that folder to an agent (e.g. add it as a skill in Claude Code),
the agent reads SKILL.md and writes Node.js playback hooks into settings.json.
For a "random" action the hook points at the action's folder and Node.js picks a
random file on each invocation.

Run with no arguments for the interactive menu, or use the subcommands
(`list`, `folders`, `set`, `add`, `remove`, `generate`) for scripting/testing.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import random
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Optional

# --------------------------------------------------------------------------- #
# Domain model
# --------------------------------------------------------------------------- #

# Claude Code hook events. The first three are the actions named in the task;
# the rest are offered because the action set is extensible.
HOOK_EVENTS: list[str] = [
    "Stop",            # the agent finished responding -> "task complete"
    "Notification",    # the agent needs the user's attention -> "asks a question"
    "SessionStart",    # a session begins -> "session start"
    "SubagentStop",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PreCompact",
    "SessionEnd",
]

# Events that take a tool-name matcher. Other events ignore matchers.
MATCHER_EVENTS = {"PreToolUse", "PostToolUse"}

AUDIO_EXTS = {".wav", ".mp3"}

CONFIG_FILENAME = "notifications.json"
SOUNDS_DIRNAME = "sounds"            # parent of the per-action folders
DEFAULT_OUTPUT_DIRNAME = "agent-notifications-skill"

# Folder name used when installing the generated skill into the global skills
# directory. Matches the `name:` in the generated SKILL.md so Claude Code lists
# it as the `agent-notifications` skill.
SKILL_NAME = "agent-notifications"

# Sound selection modes
MODE_NONE = ""
MODE_SINGLE = "single"
MODE_RANDOM = "random"


def app_base_dir() -> str:
    """Directory of the running app - the packaged .exe dir, or this script's dir.

    The per-action sound folders live under here so users always know where to
    drop their files.
    """
    if getattr(sys, "frozen", False):  # PyInstaller / similar
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def list_sounds(folder: str) -> list[str]:
    """Return sorted .wav/.mp3 filenames present in a folder (non-recursive)."""
    if not os.path.isdir(folder):
        return []
    return sorted(
        f for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() in AUDIO_EXTS
        and os.path.isfile(os.path.join(folder, f))
    )


@dataclass
class Action:
    """One configurable action: an agent event with its own sound folder."""

    id: str
    label: str
    hook_event: str
    matcher: str = ""               # only meaningful for tool events
    sound_mode: str = MODE_NONE     # "", "single" or "random"
    sound_file: str = ""            # chosen filename (single mode only)

    # -- folders ----------------------------------------------------------
    def folder_rel(self) -> str:
        """Folder of this action's sounds, relative to the app/skill root."""
        return f"{SOUNDS_DIRNAME}/{self.id}"

    def folder(self, base_dir: str) -> str:
        """Absolute folder for this action's sounds under base_dir."""
        return os.path.join(base_dir, SOUNDS_DIRNAME, self.id)

    # -- selection state --------------------------------------------------
    def is_configured(self) -> bool:
        """True if this action will emit a hook (a file or random is chosen)."""
        if self.sound_mode == MODE_RANDOM:
            return True
        return self.sound_mode == MODE_SINGLE and bool(self.sound_file)

    def describe_sound(self) -> str:
        if self.sound_mode == MODE_RANDOM:
            return f"random ({self.folder_rel()})"
        if self.sound_mode == MODE_SINGLE and self.sound_file:
            return f"{self.folder_rel()}/{self.sound_file}"
        return "(not set)"

    # -- serialization ----------------------------------------------------
    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Action":
        return cls(
            id=data["id"],
            label=data["label"],
            hook_event=data["hook_event"],
            matcher=data.get("matcher", ""),
            sound_mode=data.get("sound_mode", MODE_NONE),
            sound_file=data.get("sound_file", ""),
        )


def default_actions() -> list[Action]:
    """The three actions named in the task spec."""
    return [
        Action(id="task-complete", label="Task complete", hook_event="Stop"),
        Action(id="question", label="Agent asks a question", hook_event="Notification"),
        Action(id="session-start", label="Session start", hook_event="SessionStart"),
    ]


@dataclass
class NotificationConfig:
    """The whole configuration: an ordered list of actions."""

    actions: list[Action] = field(default_factory=default_actions)

    # -- lookup -----------------------------------------------------------
    def find(self, action_id: str) -> Optional[Action]:
        for a in self.actions:
            if a.id == action_id:
                return a
        return None

    # -- folders ----------------------------------------------------------
    def ensure_folders(self, base_dir: str) -> None:
        """Create the per-action sound folder for every action."""
        for a in self.actions:
            os.makedirs(a.folder(base_dir), exist_ok=True)

    # -- persistence ------------------------------------------------------
    def to_dict(self) -> dict:
        return {"version": 2, "actions": [a.to_dict() for a in self.actions]}

    @classmethod
    def from_dict(cls, data: dict) -> "NotificationConfig":
        actions = [Action.from_dict(a) for a in data.get("actions", [])]
        return cls(actions=actions or default_actions())

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)
            fh.write("\n")

    @classmethod
    def load(cls, path: str) -> "NotificationConfig":
        if not os.path.exists(path):
            return cls()
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))


# --------------------------------------------------------------------------- #
# Generation: build the artifacts that make up a skill folder
# --------------------------------------------------------------------------- #

PLAY_SOUND_JS = r'''#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

function fail(message) {
  console.error(`play_sound.js: ${message}`);
  process.exit(1);
}

function option(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

let sound = option("--path");
const folder = option("--folder");
if (folder) {
  if (!fs.existsSync(folder) || !fs.statSync(folder).isDirectory()) {
    fail(`folder not found: ${folder}`);
  }
  const files = fs.readdirSync(folder)
    .filter((name) => [".wav", ".mp3"].includes(path.extname(name).toLowerCase()))
    .sort();
  if (!files.length) fail(`no .wav/.mp3 files in ${folder}`);
  const index = process.argv.includes("--random")
    ? Math.floor(Math.random() * files.length) : 0;
  sound = path.join(folder, files[index]);
}
if (!sound) fail("provide --path <file> or --folder <dir> [--random]");
sound = path.resolve(sound);
if (!fs.existsSync(sound) || !fs.statSync(sound).isFile()) {
  fail(`sound file not found: ${sound}`);
}

let players;
if (process.platform === "darwin") {
  players = [["afplay", [sound]]];
} else if (process.platform === "win32") {
  // `start` uses the registered Windows audio application.
  players = [["cmd.exe", ["/d", "/s", "/c", "start", "", "/wait", sound]]];
} else {
  players = [
    ["paplay", [sound]],
    ["aplay", [sound]],
    ["ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet", sound]],
    ["mpv", ["--no-video", "--really-quiet", sound]],
    ["play", ["-q", sound]],
  ];
}

for (const [command, args] of players) {
  const result = spawnSync(command, args, { stdio: "ignore", windowsHide: true });
  if (!result.error && result.status === 0) process.exit(0);
  if (result.error && result.error.code === "ENOENT") continue;
}
fail(`no working audio player found for ${process.platform}`);
'''

_NODE_PREFIX = 'node'


def hook_command(skill_dir: str, action: Action) -> str:
    """Build the cross-platform Node.js command for a single action's hook."""
    folder = action.folder_rel()
    if action.sound_mode == MODE_RANDOM:
        return f'{_NODE_PREFIX} "{skill_dir}/play_sound.js" --folder "{skill_dir}/{folder}" --random'
    return f'{_NODE_PREFIX} "{skill_dir}/play_sound.js" --path "{skill_dir}/{folder}/{action.sound_file}"'


def build_hooks_block(config: NotificationConfig, skill_dir: str = "<SKILL_DIR>") -> dict:
    """Build the Claude Code settings `hooks` object for the configured actions.

    Only actions that have a sound selected (specific or random) are emitted.
    Multiple actions sharing a hook event are appended to that event's array.
    """
    hooks: dict[str, list] = {}
    for action in config.actions:
        if not action.is_configured():
            continue
        entry: dict = {"hooks": [{"type": "command", "command": hook_command(skill_dir, action)}]}
        if action.hook_event in MATCHER_EVENTS:
            entry = {"matcher": action.matcher or "*", **entry}
        hooks.setdefault(action.hook_event, []).append(entry)
    return {"hooks": hooks}


def build_skill_md(config: NotificationConfig) -> str:
    """Render SKILL.md - the doc an agent reads to install the hooks."""
    rows = ["| Action | Hook event | Sound source |", "|--------|-----------|--------------|"]
    for a in config.actions:
        matcher = f" (matcher: `{a.matcher}`)" if a.hook_event in MATCHER_EVENTS and a.matcher else ""
        rows.append(f"| {a.label} | `{a.hook_event}`{matcher} | `{a.describe_sound()}` |")
    table = "\n".join(rows)

    hooks_json = json.dumps(build_hooks_block(config), indent=2)

    configured = [a for a in config.actions if a.is_configured()]
    example_folder = configured[0].folder_rel() if configured else "sounds/task-complete"

    return f"""---
name: agent-notifications
description: >-
  Play sound notifications for agent lifecycle events. When this skill folder is
  available and the user asks to enable (or disable) notification sounds, create
  (or remove) Claude Code hooks that play a sound for each action via Node.js.
  Each action has its own folder under sounds/<action-id>; a "random" action plays
  a random file from its folder each time. Covers task complete (Stop), question
  asked (Notification), session start (SessionStart), and any custom actions below.
---

# Agent Notifications

This skill maps agent lifecycle **actions** to **sound folders** and tells you how
to wire them up as cross-platform Claude Code hooks that run through Node.js.

Each action owns a folder `sounds/<action-id>/` next to this file. An action is
either set to a **specific file** in its folder or to **random** (Node.js picks
a different file from the folder on every play). The configurator that produced
this folder does **not** edit settings itself - installing the hooks is your job,
performed only when the user asks.

## Action -> hook event -> sound source

{table}

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
   backslashes inside JSON, e.g. `C:\\\\Users\\\\me\\\\agent-notifications-skill`).
   If a hook event already exists in the file, **append** to its array instead of
   overwriting it.
4. Confirm the merged JSON is valid, then tell the user to restart or reload
   Claude Code so the hooks take effect.

```json
{hooks_json}
```

`play_sound.js` resolves the sound: `--path <file>` plays that file; `--folder
<dir> --random` plays a random `.wav`/`.mp3` from the folder on each invocation.

## Removing the hooks

To disable notifications, remove the hook entries whose `command` references this
skill folder's `play_sound.js` from the settings file, leaving any unrelated
hooks intact.

## Testing playback manually

```
node "<SKILL_DIR>/play_sound.js" --folder "<SKILL_DIR>/{example_folder}" --random
```

## Notes

- Requires Node.js 14 or newer. Playback uses `afplay` on macOS, the registered
  media application on Windows, and an available `paplay`, `aplay`, `ffplay`,
  `mpv`, or `play` command on Linux.
- The hook waits for playback to finish. Keep notification clips short.
- Available hook events: {", ".join(f"`{e}`" for e in HOOK_EVENTS)}.
"""


def generate_skill(config: NotificationConfig, output_dir: str, base_dir: str) -> str:
    """Write the skill folder: SKILL.md, notifications.json, play_sound.js and a
    copy of every action's sounds/<id>/ folder.

    base_dir is where the live per-action folders are read from (the app dir).
    Returns the absolute path of the generated folder. Raises if an action is
    configured but its folder lacks the needed sound(s).
    """
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    for action in config.actions:
        src_folder = action.folder(base_dir)
        dest_folder = os.path.join(output_dir, SOUNDS_DIRNAME, action.id)
        os.makedirs(dest_folder, exist_ok=True)

        available = list_sounds(src_folder)

        # Validate the selection against what's actually in the folder.
        if action.sound_mode == MODE_RANDOM and not available:
            raise FileNotFoundError(
                f"Action '{action.id}' is set to random but its folder is empty: {src_folder}"
            )
        if action.sound_mode == MODE_SINGLE and action.sound_file and action.sound_file not in available:
            raise FileNotFoundError(
                f"Action '{action.id}' selected '{action.sound_file}' which is not in {src_folder}"
            )

        # Copy the sound files so the skill folder is self-contained. For a single
        # selection only that file is needed; for random, copy them all.
        to_copy = available if action.sound_mode == MODE_RANDOM else (
            [action.sound_file] if (action.sound_mode == MODE_SINGLE and action.sound_file) else []
        )
        for name in to_copy:
            shutil.copyfile(os.path.join(src_folder, name), os.path.join(dest_folder, name))

    # play_sound.js
    with open(os.path.join(output_dir, "play_sound.js"), "w", encoding="utf-8") as fh:
        fh.write(PLAY_SOUND_JS)

    # notifications.json (same selections; folders are relative by construction)
    config.save(os.path.join(output_dir, CONFIG_FILENAME))

    # SKILL.md
    with open(os.path.join(output_dir, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(build_skill_md(config))

    return output_dir


def global_skills_dir() -> str:
    """The user's global Claude Code skills directory (~/.claude/skills)."""
    return os.path.join(os.path.expanduser("~"), ".claude", "skills")


def install_skill_global(
    config: NotificationConfig,
    base_dir: str,
    skills_dir: Optional[str] = None,
) -> str:
    """Generate the skill and install it under the global skills folder.

    The skill is written to `<skills_dir>/agent-notifications/`, replacing any
    existing folder of that name. Generation happens in a temporary directory
    first so a validation error (e.g. a "random" action with an empty folder)
    leaves any existing install untouched. Returns the installed folder path.
    """
    skills_dir = skills_dir or global_skills_dir()
    target = os.path.join(skills_dir, SKILL_NAME)

    staging = tempfile.mkdtemp(prefix="agent-notifications-skill-")
    try:
        generate_skill(config, staging, base_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    os.makedirs(skills_dir, exist_ok=True)
    if os.path.exists(target):
        shutil.rmtree(target)
    shutil.move(staging, target)
    return target


# --------------------------------------------------------------------------- #
# Interactive terminal UI
# --------------------------------------------------------------------------- #

def _prompt(msg: str) -> str:
    try:
        return input(msg).strip()
    except EOFError:
        return ""


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024 or unit == "MB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n/1024 if unit=='KB' else n/1024/1024:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def _print_actions(config: NotificationConfig) -> None:
    print("\nActions:")
    if not config.actions:
        print("  (none - add one with 'a')")
        return
    for i, a in enumerate(config.actions, 1):
        print(f"  {i}. {a.label:<24} [{a.hook_event}]  sound: {a.describe_sound()}")


def _configure_sound(action: Action, base_dir: str) -> None:
    """Show the action's folder, list available sounds, let the user choose."""
    folder = action.folder(base_dir)
    os.makedirs(folder, exist_ok=True)
    sounds = list_sounds(folder)

    print(f"\n--- Sound for '{action.label}' ---")
    print(f"Folder: {folder}")
    print(f"Current selection: {action.describe_sound()}")
    if not sounds:
        print("\nNo .wav/.mp3 files here yet.")
        print(f"Drop sound files into the folder above, then choose this action again.")
        return

    print("\nAvailable sounds:")
    for i, name in enumerate(sounds, 1):
        size = os.path.getsize(os.path.join(folder, name))
        marker = "  <- current" if (action.sound_mode == MODE_SINGLE and action.sound_file == name) else ""
        print(f"  {i}. {name}  ({_human_size(size)}){marker}")

    rand_marker = "  <- current" if action.sound_mode == MODE_RANDOM else ""
    print(f"\n  r. Random  - play a random sound from this folder each time{rand_marker}")
    print("  n. None    - disable this action")
    choice = _prompt("Choose [#/r/n] (blank to keep): ").lower()

    if choice == "":
        return
    if choice == "r":
        action.sound_mode = MODE_RANDOM
        action.sound_file = ""
        print(f"+ '{action.label}' set to RANDOM ({len(sounds)} sound(s)).")
    elif choice == "n":
        action.sound_mode = MODE_NONE
        action.sound_file = ""
        print(f"- '{action.label}' disabled.")
    elif choice.isdigit() and 1 <= int(choice) <= len(sounds):
        action.sound_mode = MODE_SINGLE
        action.sound_file = sounds[int(choice) - 1]
        print(f"+ '{action.label}' set to '{action.sound_file}'.")
    else:
        print("! Invalid choice.")


def _choose_event() -> Optional[str]:
    print("\nHook event:")
    for i, e in enumerate(HOOK_EVENTS, 1):
        print(f"  {i}. {e}")
    raw = _prompt("Choose event number: ")
    if not raw.isdigit() or not (1 <= int(raw) <= len(HOOK_EVENTS)):
        print("! Invalid choice.")
        return None
    return HOOK_EVENTS[int(raw) - 1]


def _add_action(config: NotificationConfig, base_dir: str) -> None:
    label = _prompt("\nNew action label (e.g. 'Subagent done'): ").strip()
    if not label:
        print("! Cancelled.")
        return
    action_id = _prompt("Action id (kebab-case, blank = auto): ").strip()
    if not action_id:
        action_id = "".join(c if c.isalnum() else "-" for c in label.lower()).strip("-")
    if config.find(action_id):
        print(f"! An action with id '{action_id}' already exists.")
        return
    event = _choose_event()
    if not event:
        return
    matcher = ""
    if event in MATCHER_EVENTS:
        matcher = _prompt("Tool matcher (e.g. 'Bash', '*' for all): ").strip() or "*"
    action = Action(id=action_id, label=label, hook_event=event, matcher=matcher)
    config.actions.append(action)
    folder = action.folder(base_dir)
    os.makedirs(folder, exist_ok=True)
    print(f"+ Added '{label}' [{event}]. Created folder:\n    {folder}")
    print("  Drop .wav/.mp3 files there, then pick a sound for it.")
    _configure_sound(action, base_dir)


def _remove_action(config: NotificationConfig) -> None:
    raw = _prompt("\nAction number to remove: ")
    if not raw.isdigit() or not (1 <= int(raw) <= len(config.actions)):
        print("! Invalid choice.")
        return
    removed = config.actions.pop(int(raw) - 1)
    print(f"- Removed '{removed.label}' (its sound folder was left on disk).")


def _generate(config: NotificationConfig, default_dir: str, base_dir: str) -> None:
    raw = _prompt(f"\nOutput folder [{default_dir}]: ").strip('"').strip()
    out = os.path.abspath(os.path.expanduser(raw)) if raw else default_dir
    try:
        path = generate_skill(config, out, base_dir)
    except FileNotFoundError as exc:
        print(f"! {exc}")
        return
    print(f"\n+ Skill folder generated at:\n    {path}")
    print("  Hand this folder to your agent and ask it to enable notifications.")


def _implement(config: NotificationConfig, base_dir: str) -> None:
    target = os.path.join(global_skills_dir(), SKILL_NAME)
    if os.path.isdir(target):
        print(f"\nOverwriting existing skill at:\n    {target}")
    try:
        path = install_skill_global(config, base_dir)
    except FileNotFoundError as exc:
        print(f"! {exc}")
        return
    print(f"\n+ Skill generated and installed to the global skills folder:\n    {path}")
    print("  Restart/reload Claude Code, then ask your agent to enable notifications.")


def run_menu(config: NotificationConfig, config_path: str, default_output: str, base_dir: str) -> None:
    print("=" * 64)
    print(" Agent Notifications - sound notifications for agent events")
    print("=" * 64)
    print(f" Sound folders live under: {os.path.join(base_dir, SOUNDS_DIRNAME)}")
    config.ensure_folders(base_dir)
    dirty = False
    while True:
        _print_actions(config)
        print(
            "\nMenu:  [#] choose sound   a add   d delete   g generate skill\n"
            "       i generate&implement (install to global skills)   s save   q quit"
        )
        choice = _prompt("> ").lower()

        if choice == "q":
            if dirty and _prompt("Unsaved changes - save first? (Y/n): ").lower() != "n":
                config.save(config_path)
                print(f"Saved {config_path}")
            print("Bye.")
            return
        elif choice == "s":
            config.save(config_path)
            dirty = False
            print(f"+ Saved {config_path}")
        elif choice == "a":
            _add_action(config, base_dir)
            dirty = True
        elif choice == "d":
            _remove_action(config)
            dirty = True
        elif choice == "g":
            _generate(config, default_output, base_dir)
        elif choice == "i":
            _implement(config, base_dir)
        elif choice.isdigit() and 1 <= int(choice) <= len(config.actions):
            _configure_sound(config.actions[int(choice) - 1], base_dir)
            dirty = True
        else:
            print("! Unknown choice.")


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent_notifications",
        description="Configure per-action sound folders for agent lifecycle events "
        "and generate a skill folder an agent can use to install hooks.",
    )
    p.add_argument("--config", default=None, help="Path to notifications.json (default: alongside this app)")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("list", help="List configured actions")
    sub.add_parser("folders", help="Print each action's sound folder and its files")

    s = sub.add_parser("set", help="Choose the sound for an action")
    s.add_argument("action_id")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--file", help="Use this filename from the action's folder")
    g.add_argument("--random", action="store_true", help="Play a random sound from the folder each time")
    g.add_argument("--none", action="store_true", help="Disable the action")

    a = sub.add_parser("add", help="Add a custom action (creates its folder)")
    a.add_argument("--id", required=True)
    a.add_argument("--label", required=True)
    a.add_argument("--event", required=True, choices=HOOK_EVENTS)
    a.add_argument("--matcher", default="")

    r = sub.add_parser("remove", help="Remove an action by id")
    r.add_argument("action_id")

    gen = sub.add_parser("generate", help="Generate the skill folder")
    gen.add_argument("--output", default=None, help="Output folder")

    impl = sub.add_parser(
        "implement",
        help="Generate the skill and install it into the global skills folder",
    )
    impl.add_argument(
        "--skills-dir",
        default=None,
        help="Override the global skills directory (default: ~/.claude/skills)",
    )

    return p


def main(argv: Optional[list[str]] = None, base_dir: Optional[str] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(argv)

    base_dir = base_dir or app_base_dir()
    config_path = args.config or os.path.join(base_dir, CONFIG_FILENAME)
    default_output = os.path.join(base_dir, DEFAULT_OUTPUT_DIRNAME)
    config = NotificationConfig.load(config_path)
    config.ensure_folders(base_dir)

    cmd = args.command
    if cmd is None:
        run_menu(config, config_path, default_output, base_dir)
        return 0

    if cmd == "list":
        _print_actions(config)
        return 0

    if cmd == "folders":
        for a in config.actions:
            folder = a.folder(base_dir)
            sounds = list_sounds(folder)
            print(f"{a.id}: {folder}")
            for name in sounds:
                print(f"    - {name}")
            if not sounds:
                print("    (empty - drop .wav/.mp3 files here)")
        return 0

    if cmd == "set":
        action = config.find(args.action_id)
        if not action:
            print(f"! No action with id '{args.action_id}'.", file=sys.stderr)
            return 1
        if args.none:
            action.sound_mode, action.sound_file = MODE_NONE, ""
        elif args.random:
            action.sound_mode, action.sound_file = MODE_RANDOM, ""
        else:  # --file
            available = list_sounds(action.folder(base_dir))
            if args.file not in available:
                print(f"! '{args.file}' not found in {action.folder(base_dir)}", file=sys.stderr)
                return 1
            action.sound_mode, action.sound_file = MODE_SINGLE, args.file
        config.save(config_path)
        print(f"+ '{args.action_id}' -> {action.describe_sound()}")
        return 0

    if cmd == "add":
        if config.find(args.id):
            print(f"! Action id '{args.id}' already exists.", file=sys.stderr)
            return 1
        action = Action(id=args.id, label=args.label, hook_event=args.event, matcher=args.matcher)
        config.actions.append(action)
        os.makedirs(action.folder(base_dir), exist_ok=True)
        config.save(config_path)
        print(f"+ Added '{args.id}'. Folder: {action.folder(base_dir)}")
        return 0

    if cmd == "remove":
        action = config.find(args.action_id)
        if not action:
            print(f"! No action with id '{args.action_id}'.", file=sys.stderr)
            return 1
        config.actions.remove(action)
        config.save(config_path)
        print(f"- Removed '{args.action_id}'.")
        return 0

    if cmd == "generate":
        out = args.output or default_output
        try:
            path = generate_skill(config, out, base_dir)
        except FileNotFoundError as exc:
            print(f"! {exc}", file=sys.stderr)
            return 1
        print(f"+ Skill folder generated at: {path}")
        return 0

    if cmd == "implement":
        try:
            path = install_skill_global(config, base_dir, skills_dir=args.skills_dir)
        except FileNotFoundError as exc:
            print(f"! {exc}", file=sys.stderr)
            return 1
        print(f"+ Skill installed to global skills folder: {path}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
