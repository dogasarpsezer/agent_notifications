#!/usr/bin/env node
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
