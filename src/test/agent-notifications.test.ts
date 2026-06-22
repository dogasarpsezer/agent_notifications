import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { Action, MODE_RANDOM, MODE_SINGLE, NotificationConfig, PLAY_SOUND_JS, buildHooksBlock, buildSkillMd, generateSkill, installSkillGlobal, listSounds } from "../agent-notifications.js";
import { main } from "../cli.js";

function temp(): string { return mkdtempSync(join(tmpdir(), "agent-notifications-test-")); }
function wav(folder: string, name: string): void { mkdirSync(folder, { recursive: true }); writeFileSync(join(folder, name), "RIFF....WAVEfmt "); }

test("default model and sound discovery", () => {
  const config = new NotificationConfig();
  assert.deepEqual(config.actions.map((a) => a.id), ["task-complete", "question", "session-start"]);
  const dir = temp(); wav(dir, "b.wav"); wav(dir, "a.mp3"); writeFileSync(join(dir, "x.txt"), "x");
  assert.deepEqual(listSounds(dir), ["a.mp3", "b.wav"]);
});

test("configuration round trips", () => {
  const dir = temp(); const path = join(dir, "notifications.json"); const config = new NotificationConfig();
  config.actions[0].sound_mode = MODE_RANDOM; config.save(path);
  assert.equal(NotificationConfig.load(path).actions[0].sound_mode, MODE_RANDOM);
});

test("hook generation handles random, single, and matchers", () => {
  const config = new NotificationConfig([new Action({ id: "pre", label: "Pre", hook_event: "PreToolUse", matcher: "Bash", sound_mode: MODE_RANDOM })]);
  const entry = buildHooksBlock(config).hooks.PreToolUse[0];
  assert.equal(entry.matcher, "Bash"); assert.match(entry.hooks[0].command, /--folder .* --random/);
  config.actions[0].sound_mode = MODE_SINGLE; config.actions[0].sound_file = "a.wav";
  assert.match(buildHooksBlock(config).hooks.PreToolUse[0].hooks[0].command, /--path .*a\.wav/);
  assert.doesNotThrow(() => JSON.parse(buildSkillMd(config).split("```json")[1].split("```")[0]));
});

test("SessionStart matcher scopes settings and self-filters on source", () => {
  const config = new NotificationConfig([new Action({ id: "session-start", label: "Session start", hook_event: "SessionStart", matcher: "startup", sound_mode: MODE_SINGLE, sound_file: "a.mp3" })]);
  const entry = buildHooksBlock(config).hooks.SessionStart[0];
  assert.equal(entry.matcher, "startup");
  assert.match(entry.hooks[0].command, /--require-source "startup"/);
  assert.match(PLAY_SOUND_JS, /--require-source/);
});

test("volume flag flows into hook command and player script", () => {
  const config = new NotificationConfig([new Action({ id: "question", label: "Q", hook_event: "Notification", sound_mode: MODE_SINGLE, sound_file: "q.mp3", volume: 50 })]);
  assert.match(buildHooksBlock(config).hooks.Notification[0].hooks[0].command, /--volume 50/);
  assert.match(PLAY_SOUND_JS, /--volume/);
  assert.match(PLAY_SOUND_JS, /setaudio/);
  const full = new NotificationConfig([new Action({ id: "question", label: "Q", hook_event: "Notification", sound_mode: MODE_SINGLE, sound_file: "q.mp3" })]);
  assert.equal(full.actions[0].volume, 100);
  assert.doesNotMatch(buildHooksBlock(full).hooks.Notification[0].hooks[0].command, /--volume/);
});

test("Windows playback is hidden and does not launch a media player", () => {
  assert.match(PLAY_SOUND_JS, /mciSendString/);
  assert.match(PLAY_SOUND_JS, /-WindowStyle.*Hidden/);
  assert.doesNotMatch(PLAY_SOUND_JS, /cmd\.exe|\"start\"/);
});

test("skill generation copies selected sounds", () => {
  const base = temp(); const config = new NotificationConfig(); config.ensureFolders(base);
  wav(config.actions[0].folder(base), "a.wav"); wav(config.actions[0].folder(base), "b.wav"); config.actions[0].sound_mode = MODE_RANDOM;
  const out = generateSkill(config, join(base, "skill"), base);
  assert.deepEqual(readdirSync(join(out, "sounds", "task-complete")), ["a.wav", "b.wav"]);
  assert.match(readFileSync(join(out, "SKILL.md"), "utf8"), /name: agent-notifications/);
  assert.equal(JSON.parse(readFileSync(join(out, "package.json"), "utf8")).type, "commonjs");
});

test("invalid selection does not replace an installed skill", () => {
  const base = temp(); const config = new NotificationConfig(); config.ensureFolders(base); wav(config.actions[0].folder(base), "done.wav"); config.actions[0].sound_mode = MODE_RANDOM;
  const installed = installSkillGlobal(config, base, join(base, "skills")); writeFileSync(join(installed, "marker"), "keep");
  config.actions[1].sound_mode = MODE_RANDOM;
  assert.throws(() => installSkillGlobal(config, base, join(base, "skills")), /folder is empty/);
  assert.equal(readFileSync(join(installed, "marker"), "utf8"), "keep");
});

test("CLI set and generate workflow", async () => {
  const base = temp(); const configPath = join(base, "notifications.json");
  assert.equal(await main(["--config", configPath, "list"], base), 0);
  wav(join(base, "sounds", "task-complete"), "done.wav");
  assert.equal(await main(["--config", configPath, "set", "task-complete", "--random"], base), 0);
  assert.equal(await main(["--config", configPath, "generate", "--output", join(base, "skill")], base), 0);
});
