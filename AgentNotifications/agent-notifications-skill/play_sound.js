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
  // Use Windows' built-in MCI API through a hidden PowerShell process. This
  // supports WAV and MP3 without opening the registered media player.
  const escapedSound = sound.replace(/'/g, "''");
  const script = [
    "Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class NativeAudio { [DllImport(\"winmm.dll\", CharSet=CharSet.Unicode)] public static extern int mciSendString(string command, IntPtr buffer, int bufferSize, IntPtr callback); }'",
    `$path = '${escapedSound}'`,
    "$alias = 'AgentNotification'",
    "$open = [NativeAudio]::mciSendString(('open \"' + $path + '\" alias ' + $alias), [IntPtr]::Zero, 0, [IntPtr]::Zero)",
    "if ($open -ne 0) { exit $open }",
    "try { $play = [NativeAudio]::mciSendString(('play ' + $alias + ' wait'), [IntPtr]::Zero, 0, [IntPtr]::Zero); if ($play -ne 0) { exit $play } }",
    "finally { [void][NativeAudio]::mciSendString(('close ' + $alias), [IntPtr]::Zero, 0, [IntPtr]::Zero) }",
  ].join("\n");
  const encoded = Buffer.from(script, "utf16le").toString("base64");
  players = [["powershell.exe", ["-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded]]];
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
