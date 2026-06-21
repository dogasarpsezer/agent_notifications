#!/usr/bin/env node
import { createInterface } from "node:readline/promises";
import { stdin, stdout } from "node:process";
import { mkdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import {
  Action, CONFIG_FILENAME, DEFAULT_OUTPUT_DIRNAME, HOOK_EVENTS, MATCHER_EVENTS, MODE_NONE, MODE_RANDOM, MODE_SINGLE,
  NotificationConfig, appBaseDir, formatActions, generateSkill, globalSkillsDir, humanSize,
  installSkillGlobal, isHookEvent, listSounds, validateActionId,
} from "./agent-notifications.js";

interface Parsed { config?: string; command?: string; positionals: string[]; options: Map<string, string | boolean> }

function parseArgs(argv: string[]): Parsed {
  const parsed: Parsed = { positionals: [], options: new Map() };
  for (let i = 0; i < argv.length; i++) {
    const value = argv[i];
    if (value === "--config") parsed.config = argv[++i];
    else if (!parsed.command && !value.startsWith("-")) parsed.command = value;
    else if (value.startsWith("--")) {
      const next = argv[i + 1];
      parsed.options.set(value, next && !next.startsWith("--") ? argv[++i] : true);
    } else parsed.positionals.push(value);
  }
  return parsed;
}

function help(): void {
  console.log(`Usage: agent-notifications [--config <path>] [command]

Commands:
  list
  folders
  set <id> (--file <name> | --random | --none)
  add --id <id> --label <text> --event <event> [--matcher <matcher>]
  remove <id>
  generate [--output <dir>]
  implement [--skills-dir <dir>]

Run without a command for the interactive menu.`);
}

function optionString(parsed: Parsed, name: string): string | undefined {
  const value = parsed.options.get(name);
  return typeof value === "string" ? value : undefined;
}

async function runMenu(config: NotificationConfig, configPath: string, defaultOutput: string, baseDir: string): Promise<void> {
  const rl = createInterface({ input: stdin, output: stdout });
  let dirty = false;
  console.log(`${"=".repeat(64)}\n Agent Notifications - sound notifications for agent events\n${"=".repeat(64)}`);
  console.log(` Sound folders live under: ${join(baseDir, "sounds")}`);
  try {
    while (true) {
      console.log(formatActions(config));
      console.log("\nMenu:  [#] choose sound   a add   d delete   g generate skill\n       i generate&implement   s save   q quit");
      const choice = (await rl.question("> ")).trim().toLowerCase();
      if (choice === "q") {
        if (dirty && (await rl.question("Unsaved changes - save first? (Y/n): ")).trim().toLowerCase() !== "n") config.save(configPath);
        console.log("Bye."); return;
      }
      if (choice === "s") { config.save(configPath); dirty = false; console.log(`+ Saved ${configPath}`); continue; }
      if (choice === "g") {
        const raw = (await rl.question(`Output folder [${defaultOutput}]: `)).trim().replace(/^"|"$/g, "");
        try { console.log(`+ Skill folder generated at: ${generateSkill(config, raw ? resolve(raw) : defaultOutput, baseDir)}`); } catch (error) { console.error(`! ${(error as Error).message}`); }
        continue;
      }
      if (choice === "i") {
        try { console.log(`+ Skill installed to global skills folder: ${installSkillGlobal(config, baseDir)}`); } catch (error) { console.error(`! ${(error as Error).message}`); }
        continue;
      }
      if (choice === "a") {
        const label = (await rl.question("New action label: ")).trim();
        let id = (await rl.question("Action id (kebab-case, blank = auto): ")).trim() || label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
        if (!label || !validateActionId(id) || config.find(id)) { console.error("! Invalid, empty, or duplicate action."); continue; }
        HOOK_EVENTS.forEach((event, i) => console.log(`  ${i + 1}. ${event}`));
        const event = HOOK_EVENTS[Number(await rl.question("Choose event number: ")) - 1];
        if (!event) { console.error("! Invalid choice."); continue; }
        const matcher = MATCHER_EVENTS.has(event) ? (await rl.question("Tool matcher [*]: ")).trim() || "*" : "";
        const action = new Action({ id, label, hook_event: event, matcher }); config.actions.push(action); mkdirSync(action.folder(baseDir), { recursive: true });
        dirty = true; console.log(`+ Added '${id}'. Folder: ${action.folder(baseDir)}`); continue;
      }
      if (choice === "d") {
        const index = Number(await rl.question("Action number to remove: ")) - 1;
        if (index < 0 || index >= config.actions.length) console.error("! Invalid choice.");
        else { console.log(`- Removed '${config.actions.splice(index, 1)[0].label}'.`); dirty = true; }
        continue;
      }
      const index = Number(choice) - 1;
      if (Number.isInteger(index) && index >= 0 && index < config.actions.length) {
        const action = config.actions[index]; const sounds = listSounds(action.folder(baseDir));
        console.log(`\nFolder: ${action.folder(baseDir)}\nCurrent selection: ${action.describeSound()}`);
        if (!sounds.length) { console.log("No .wav/.mp3 files here yet."); continue; }
        sounds.forEach((name, i) => console.log(`  ${i + 1}. ${name} (${humanSize(statSync(join(action.folder(baseDir), name)).size)})`));
        const selection = (await rl.question("Choose [#/r/n] (blank to keep): ")).trim().toLowerCase();
        if (selection === "r") { action.sound_mode = MODE_RANDOM; action.sound_file = ""; }
        else if (selection === "n") { action.sound_mode = MODE_NONE; action.sound_file = ""; }
        else if (Number(selection) >= 1 && Number(selection) <= sounds.length) { action.sound_mode = MODE_SINGLE; action.sound_file = sounds[Number(selection) - 1]; }
        else if (selection) { console.error("! Invalid choice."); continue; }
        dirty ||= Boolean(selection); continue;
      }
      console.error("! Unknown choice.");
    }
  } finally { rl.close(); }
}

export async function main(argv = process.argv.slice(2), baseDir = appBaseDir()): Promise<number> {
  const parsed = parseArgs(argv);
  if (parsed.command === "help" || parsed.options.has("--help") || argv.includes("-h")) { help(); return 0; }
  const configPath = resolve(parsed.config ?? join(baseDir, CONFIG_FILENAME));
  const config = NotificationConfig.load(configPath); config.ensureFolders(baseDir);
  const command = parsed.command;
  if (!command) { await runMenu(config, configPath, join(baseDir, DEFAULT_OUTPUT_DIRNAME), baseDir); return 0; }
  if (command === "list") { console.log(formatActions(config)); return 0; }
  if (command === "folders") {
    for (const action of config.actions) { const folder = action.folder(baseDir); const files = listSounds(folder); console.log(`${action.id}: ${folder}`); console.log(files.length ? files.map((f) => `    - ${f}`).join("\n") : "    (empty - drop .wav/.mp3 files here)"); }
    return 0;
  }
  if (command === "set") {
    const id = parsed.positionals[0]; const action = config.find(id);
    if (!action) { console.error(`! No action with id '${id}'.`); return 1; }
    const file = optionString(parsed, "--file");
    if (parsed.options.has("--none")) { action.sound_mode = MODE_NONE; action.sound_file = ""; }
    else if (parsed.options.has("--random")) { action.sound_mode = MODE_RANDOM; action.sound_file = ""; }
    else if (file) {
      if (!listSounds(action.folder(baseDir)).includes(file)) { console.error(`! '${file}' not found in ${action.folder(baseDir)}`); return 1; }
      action.sound_mode = MODE_SINGLE; action.sound_file = file;
    } else { console.error("! set requires --file, --random, or --none."); return 1; }
    config.save(configPath); console.log(`+ '${id}' -> ${action.describeSound()}`); return 0;
  }
  if (command === "add") {
    const id = optionString(parsed, "--id"); const label = optionString(parsed, "--label"); const event = optionString(parsed, "--event");
    if (!id || !label || !event || !validateActionId(id) || !isHookEvent(event)) { console.error("! add requires a kebab-case --id, --label, and valid --event."); return 1; }
    if (config.find(id)) { console.error(`! Action id '${id}' already exists.`); return 1; }
    const action = new Action({ id, label, hook_event: event, matcher: optionString(parsed, "--matcher") ?? "" }); config.actions.push(action); mkdirSync(action.folder(baseDir), { recursive: true }); config.save(configPath); console.log(`+ Added '${id}'. Folder: ${action.folder(baseDir)}`); return 0;
  }
  if (command === "remove") {
    const id = parsed.positionals[0]; const index = config.actions.findIndex((a) => a.id === id);
    if (index < 0) { console.error(`! No action with id '${id}'.`); return 1; }
    config.actions.splice(index, 1); config.save(configPath); console.log(`- Removed '${id}'.`); return 0;
  }
  if (command === "generate") {
    try { console.log(`+ Skill folder generated at: ${generateSkill(config, optionString(parsed, "--output") ?? join(baseDir, DEFAULT_OUTPUT_DIRNAME), baseDir)}`); return 0; }
    catch (error) { console.error(`! ${(error as Error).message}`); return 1; }
  }
  if (command === "implement") {
    const skillsDir = optionString(parsed, "--skills-dir") ?? globalSkillsDir();
    try { console.log(`+ Skill installed to global skills folder: ${installSkillGlobal(config, baseDir, skillsDir)}`); return 0; }
    catch (error) { console.error(`! ${(error as Error).message}`); return 1; }
  }
  console.error(`! Unknown command '${command}'.`); help(); return 1;
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  process.exitCode = await main();
}
