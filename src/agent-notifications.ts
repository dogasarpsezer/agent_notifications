import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, rmSync, statSync, writeFileSync, copyFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { basename, dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const HOOK_EVENTS = ["Stop", "Notification", "SessionStart", "SubagentStop", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PreCompact", "SessionEnd"] as const;
export type HookEvent = (typeof HOOK_EVENTS)[number];
export const MATCHER_EVENTS = new Set<HookEvent>(["PreToolUse", "PostToolUse"]);
export const MODE_NONE = "" as const;
export const MODE_SINGLE = "single" as const;
export const MODE_RANDOM = "random" as const;
export type SoundMode = typeof MODE_NONE | typeof MODE_SINGLE | typeof MODE_RANDOM;
export const CONFIG_FILENAME = "notifications.json";
export const SOUNDS_DIRNAME = "sounds";
export const DEFAULT_OUTPUT_DIRNAME = "agent-notifications-skill";
export const SKILL_NAME = "agent-notifications";

export interface ActionData {
  id: string;
  label: string;
  hook_event: HookEvent;
  matcher?: string;
  sound_mode?: SoundMode;
  sound_file?: string;
  volume?: number;
}

export const DEFAULT_VOLUME = 100;
export function clampVolume(value: number): number { return Math.max(0, Math.min(100, Math.round(value))); }

export class Action {
  id: string;
  label: string;
  hook_event: HookEvent;
  matcher: string;
  sound_mode: SoundMode;
  sound_file: string;
  volume: number;

  constructor(data: ActionData) {
    this.id = data.id;
    this.label = data.label;
    this.hook_event = data.hook_event;
    this.matcher = data.matcher ?? "";
    this.sound_mode = data.sound_mode ?? MODE_NONE;
    this.sound_file = data.sound_file ?? "";
    this.volume = clampVolume(data.volume ?? DEFAULT_VOLUME);
  }

  folderRel(): string { return `${SOUNDS_DIRNAME}/${this.id}`; }
  folder(baseDir: string): string { return join(baseDir, SOUNDS_DIRNAME, this.id); }
  isConfigured(): boolean { return this.sound_mode === MODE_RANDOM || (this.sound_mode === MODE_SINGLE && Boolean(this.sound_file)); }
  describeSound(): string {
    const vol = this.volume !== DEFAULT_VOLUME ? ` @ ${this.volume}%` : "";
    if (this.sound_mode === MODE_RANDOM) return `random (${this.folderRel()})${vol}`;
    if (this.sound_mode === MODE_SINGLE && this.sound_file) return `${this.folderRel()}/${this.sound_file}${vol}`;
    return "(not set)";
  }
  toJSON(): Required<ActionData> {
    return { id: this.id, label: this.label, hook_event: this.hook_event, matcher: this.matcher, sound_mode: this.sound_mode, sound_file: this.sound_file, volume: this.volume };
  }
}

export function defaultActions(): Action[] {
  return [
    new Action({ id: "task-complete", label: "Task complete", hook_event: "Stop" }),
    new Action({ id: "question", label: "Agent asks a question", hook_event: "Notification" }),
    new Action({ id: "session-start", label: "Session start", hook_event: "SessionStart" }),
  ];
}

export class NotificationConfig {
  constructor(public actions: Action[] = defaultActions()) {}
  find(id: string): Action | undefined { return this.actions.find((action) => action.id === id); }
  ensureFolders(baseDir: string): void { for (const action of this.actions) mkdirSync(action.folder(baseDir), { recursive: true }); }
  toJSON(): { version: number; actions: Required<ActionData>[] } { return { version: 2, actions: this.actions.map((action) => action.toJSON()) }; }
  save(path: string): void { mkdirSync(dirname(resolve(path)), { recursive: true }); writeFileSync(path, `${JSON.stringify(this.toJSON(), null, 2)}\n`, "utf8"); }
  static from(data: { actions?: ActionData[] }): NotificationConfig {
    const actions = (data.actions ?? []).map((action) => new Action(action));
    return new NotificationConfig(actions.length ? actions : defaultActions());
  }
  static load(path: string): NotificationConfig {
    return existsSync(path) ? NotificationConfig.from(JSON.parse(readFileSync(path, "utf8")) as { actions?: ActionData[] }) : new NotificationConfig();
  }
}

export function appBaseDir(): string {
  const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
  const dataDir = join(packageRoot, "AgentNotifications");
  return existsSync(dataDir) ? dataDir : packageRoot;
}

export function listSounds(folder: string): string[] {
  if (!existsSync(folder) || !statSync(folder).isDirectory()) return [];
  return readdirSync(folder).filter((name) => [".wav", ".mp3"].includes(extname(name).toLowerCase()) && statSync(join(folder, name)).isFile()).sort();
}

export const PLAY_SOUND_JS = `#!/usr/bin/env node
"use strict";
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
function fail(message) { console.error(\`play_sound.js: \${message}\`); process.exit(1); }
function option(name) { const index = process.argv.indexOf(name); return index >= 0 ? process.argv[index + 1] : undefined; }
const requireSource = option("--require-source");
if (requireSource) {
  let source = null;
  try { source = JSON.parse(fs.readFileSync(0, "utf8")).source ?? null; } catch (e) {}
  if (source !== null && source !== requireSource) process.exit(0);
}
const volumeOpt = option("--volume");
let volume = 100;
if (volumeOpt !== undefined) { const parsed = Number(volumeOpt); if (!Number.isNaN(parsed)) volume = Math.max(0, Math.min(100, parsed)); }
let sound = option("--path");
const folder = option("--folder");
if (folder) {
  if (!fs.existsSync(folder) || !fs.statSync(folder).isDirectory()) fail(\`folder not found: \${folder}\`);
  const files = fs.readdirSync(folder).filter((name) => [".wav", ".mp3"].includes(path.extname(name).toLowerCase())).sort();
  if (!files.length) fail(\`no .wav/.mp3 files in \${folder}\`);
  sound = path.join(folder, files[process.argv.includes("--random") ? Math.floor(Math.random() * files.length) : 0]);
}
if (!sound) fail("provide --path <file> or --folder <dir> [--random]");
sound = path.resolve(sound);
if (!fs.existsSync(sound) || !fs.statSync(sound).isFile()) fail(\`sound file not found: \${sound}\`);
let players;
if (process.platform === "darwin") players = [["afplay", ["-v", String(volume / 100), sound]]];
else if (process.platform === "win32") {
  const escapedSound = sound.replace(/'/g, "''");
  const mciVolume = Math.round(volume * 10);
  const script = [
    "Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class NativeAudio { [DllImport(\\\"winmm.dll\\\", CharSet=CharSet.Unicode)] public static extern int mciSendString(string command, IntPtr buffer, int bufferSize, IntPtr callback); }'",
    \`$path = '\${escapedSound}'\`,
    "$alias = 'AgentNotification'",
    "$open = [NativeAudio]::mciSendString(('open \\\"' + $path + '\\\" alias ' + $alias), [IntPtr]::Zero, 0, [IntPtr]::Zero)",
    "if ($open -ne 0) { exit $open }",
    \`[void][NativeAudio]::mciSendString(('setaudio ' + $alias + ' volume to \${mciVolume}'), [IntPtr]::Zero, 0, [IntPtr]::Zero)\`,
    "try { $play = [NativeAudio]::mciSendString(('play ' + $alias + ' wait'), [IntPtr]::Zero, 0, [IntPtr]::Zero); if ($play -ne 0) { exit $play } }",
    "finally { [void][NativeAudio]::mciSendString(('close ' + $alias), [IntPtr]::Zero, 0, [IntPtr]::Zero) }",
  ].join("\\n");
  const encoded = Buffer.from(script, "utf16le").toString("base64");
  players = [["powershell.exe", ["-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded]]];
}
else {
  const paVolume = Math.round((volume / 100) * 65536);
  players = [
    ["paplay", [\`--volume=\${paVolume}\`, sound]],
    ["aplay", [sound]],
    ["ffplay", ["-volume", String(volume), "-nodisp", "-autoexit", "-loglevel", "quiet", sound]],
    ["mpv", [\`--volume=\${volume}\`, "--no-video", "--really-quiet", sound]],
    ["play", ["-v", String(volume / 100), "-q", sound]],
  ];
}
for (const [command, args] of players) {
  const result = spawnSync(command, args, { stdio: "ignore", windowsHide: true });
  if (!result.error && result.status === 0) process.exit(0);
  if (result.error && result.error.code === "ENOENT") continue;
}
fail(\`no working audio player found for \${process.platform}\`);
`;

export function hookCommand(skillDir: string, action: Action): string {
  let command = action.sound_mode === MODE_RANDOM
    ? `node "${skillDir}/play_sound.js" --folder "${skillDir}/${action.folderRel()}" --random`
    : `node "${skillDir}/play_sound.js" --path "${skillDir}/${action.folderRel()}/${action.sound_file}"`;
  // SessionStart fires for startup/resume/clear/compact. The settings `matcher` should scope it,
  // but some clients don't honor it, so the script also self-filters on the `source` it gets on stdin.
  if (action.hook_event === "SessionStart" && action.matcher) command += ` --require-source "${action.matcher}"`;
  if (action.volume !== DEFAULT_VOLUME) command += ` --volume ${action.volume}`;
  return command;
}

export interface HookEntry { matcher?: string; hooks: Array<{ type: "command"; command: string }> }
export function buildHooksBlock(config: NotificationConfig, skillDir = "<SKILL_DIR>"): { hooks: Record<string, HookEntry[]> } {
  const hooks: Record<string, HookEntry[]> = {};
  for (const action of config.actions) {
    if (!action.isConfigured()) continue;
    const entry: HookEntry = { hooks: [{ type: "command", command: hookCommand(skillDir, action) }] };
    if (MATCHER_EVENTS.has(action.hook_event)) entry.matcher = action.matcher || "*";
    else if (action.matcher) entry.matcher = action.matcher;
    (hooks[action.hook_event] ??= []).push(entry);
  }
  return { hooks };
}

export function buildSkillMd(config: NotificationConfig): string {
  const rows = ["| Action | Hook event | Sound source |", "|--------|-----------|--------------|", ...config.actions.map((a) => {
    const matcher = a.matcher ? ` (matcher: \`${a.matcher}\`)` : "";
    return `| ${a.label} | \`${a.hook_event}\`${matcher} | \`${a.describeSound()}\` |`;
  })];
  const configured = config.actions.filter((a) => a.isConfigured());
  const exampleFolder = configured[0]?.folderRel() ?? "sounds/task-complete";
  return `---
name: agent-notifications
description: >-
  Play sound notifications for agent lifecycle events. Create or remove hooks
  that play configured sounds through the bundled Node.js playback script.
---

# Agent Notifications

This skill maps agent lifecycle actions to sound folders and explains how to wire
them up as cross-platform hooks. The configurator does not edit settings itself.

## Action -> hook event -> sound source

${rows.join("\n")}

Actions with no sound source are skipped.

## How to install the hooks

1. Determine the absolute directory containing this \`SKILL.md\` (\`SKILL_DIR\`).
2. Use the project's \`.claude/settings.json\`, unless the user requests global settings.
3. Merge the hooks below, replacing every \`<SKILL_DIR>\` with the absolute path.
   Append entries to existing event arrays; do not overwrite unrelated hooks.
4. Validate the JSON and tell the user to restart or reload Claude Code.

\`\`\`json
${JSON.stringify(buildHooksBlock(config), null, 2)}
\`\`\`

## Removing the hooks

Remove entries whose command references this skill folder's \`play_sound.js\`.

## Testing playback manually

\`\`\`
node "<SKILL_DIR>/play_sound.js" --folder "<SKILL_DIR>/${exampleFolder}" --random
\`\`\`

Requires Node.js 18 or newer. Available hook events: ${HOOK_EVENTS.map((e) => `\`${e}\``).join(", ")}.
`;
}

export function generateSkill(config: NotificationConfig, outputDir: string, baseDir: string): string {
  const output = resolve(outputDir);
  mkdirSync(output, { recursive: true });
  for (const action of config.actions) {
    const source = action.folder(baseDir);
    const destination = join(output, SOUNDS_DIRNAME, action.id);
    mkdirSync(destination, { recursive: true });
    const available = listSounds(source);
    if (action.sound_mode === MODE_RANDOM && !available.length) throw new Error(`Action '${action.id}' is set to random but its folder is empty: ${source}`);
    if (action.sound_mode === MODE_SINGLE && action.sound_file && !available.includes(action.sound_file)) throw new Error(`Action '${action.id}' selected '${action.sound_file}' which is not in ${source}`);
    const files = action.sound_mode === MODE_RANDOM ? available : action.sound_mode === MODE_SINGLE && action.sound_file ? [action.sound_file] : [];
    for (const file of files) copyFileSync(join(source, file), join(destination, file));
  }
  writeFileSync(join(output, "play_sound.js"), PLAY_SOUND_JS, "utf8");
  writeFileSync(join(output, "package.json"), `${JSON.stringify({ private: true, type: "commonjs" }, null, 2)}\n`, "utf8");
  config.save(join(output, CONFIG_FILENAME));
  writeFileSync(join(output, "SKILL.md"), buildSkillMd(config), "utf8");
  return output;
}

export function globalSkillsDir(): string { return join(homedir(), ".claude", "skills"); }

export function installSkillGlobal(config: NotificationConfig, baseDir: string, skillsDir = globalSkillsDir()): string {
  const target = join(skillsDir, SKILL_NAME);
  const staging = join(tmpdir(), `agent-notifications-skill-${process.pid}-${Date.now()}`);
  try { generateSkill(config, staging, baseDir); }
  catch (error) { rmSync(staging, { recursive: true, force: true }); throw error; }
  mkdirSync(skillsDir, { recursive: true });
  rmSync(target, { recursive: true, force: true });
  renameSync(staging, target);
  return target;
}

export function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

export function formatActions(config: NotificationConfig): string {
  if (!config.actions.length) return "\nActions:\n  (none - add one with 'a')";
  return `\nActions:\n${config.actions.map((a, i) => `  ${i + 1}. ${a.label.padEnd(24)} [${a.hook_event}]  sound: ${a.describeSound()}`).join("\n")}`;
}

export function validateActionId(id: string): boolean { return /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id); }
export function isHookEvent(value: string): value is HookEvent { return (HOOK_EVENTS as readonly string[]).includes(value); }
export function fileName(path: string): string { return basename(path); }
