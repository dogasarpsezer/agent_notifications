#!/usr/bin/env python3
"""Tests for the Agent Notifications configurator.

Pure-Python tests (no Node.js / audio needed). Run with:

    python -m unittest test_agent_notifications -v
"""

import json
import os
import tempfile
import unittest

import agent_notifications as an


def _wav(folder: str, name: str) -> str:
    """Create a tiny placeholder file standing in for a sound."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    with open(path, "wb") as fh:
        fh.write(b"RIFF....WAVEfmt ")
    return path


class ModelTests(unittest.TestCase):
    def test_default_actions_match_spec(self):
        cfg = an.NotificationConfig()
        self.assertEqual([a.id for a in cfg.actions], ["task-complete", "question", "session-start"])
        self.assertEqual([a.hook_event for a in cfg.actions], ["Stop", "Notification", "SessionStart"])

    def test_folder_paths(self):
        a = an.Action("task-complete", "X", "Stop")
        self.assertEqual(a.folder_rel(), "sounds/task-complete")
        self.assertTrue(a.folder("/base").replace("\\", "/").endswith("sounds/task-complete"))

    def test_is_configured(self):
        self.assertFalse(an.Action("x", "X", "Stop").is_configured())
        self.assertFalse(an.Action("x", "X", "Stop", sound_mode=an.MODE_SINGLE).is_configured())
        self.assertTrue(an.Action("x", "X", "Stop", sound_mode=an.MODE_SINGLE, sound_file="a.wav").is_configured())
        self.assertTrue(an.Action("x", "X", "Stop", sound_mode=an.MODE_RANDOM).is_configured())

    def test_describe_sound(self):
        self.assertEqual(an.Action("t", "T", "Stop").describe_sound(), "(not set)")
        self.assertEqual(an.Action("t", "T", "Stop", sound_mode=an.MODE_RANDOM).describe_sound(),
                         "random (sounds/t)")
        self.assertEqual(
            an.Action("t", "T", "Stop", sound_mode=an.MODE_SINGLE, sound_file="a.wav").describe_sound(),
            "sounds/t/a.wav",
        )

    def test_roundtrip_serialization(self):
        cfg = an.NotificationConfig()
        cfg.actions[0].sound_mode = an.MODE_RANDOM
        restored = an.NotificationConfig.from_dict(json.loads(json.dumps(cfg.to_dict())))
        self.assertEqual(restored.actions[0].sound_mode, an.MODE_RANDOM)

    def test_ensure_folders_creates_per_action_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = an.NotificationConfig()
            cfg.ensure_folders(d)
            for a in cfg.actions:
                self.assertTrue(os.path.isdir(a.folder(d)), a.id)

    def test_list_sounds(self):
        with tempfile.TemporaryDirectory() as d:
            _wav(d, "b.wav")
            _wav(d, "a.mp3")
            with open(os.path.join(d, "notes.txt"), "w") as fh:
                fh.write("x")
            self.assertEqual(an.list_sounds(d), ["a.mp3", "b.wav"])  # sorted, audio only


class HooksBlockTests(unittest.TestCase):
    def test_only_configured_actions_emitted(self):
        cfg = an.NotificationConfig()
        cfg.actions[0].sound_mode = an.MODE_RANDOM
        block = an.build_hooks_block(cfg)
        self.assertIn("Stop", block["hooks"])
        self.assertNotIn("Notification", block["hooks"])

    def test_random_command_uses_folder_flag(self):
        cfg = an.NotificationConfig()
        cfg.actions[0].sound_mode = an.MODE_RANDOM
        cmd = an.build_hooks_block(cfg)["hooks"]["Stop"][0]["hooks"][0]["command"]
        self.assertIn('--folder "<SKILL_DIR>/sounds/task-complete" --random', cmd)

    def test_single_command_uses_path_flag(self):
        cfg = an.NotificationConfig()
        cfg.actions[0].sound_mode = an.MODE_SINGLE
        cfg.actions[0].sound_file = "done.wav"
        cmd = an.build_hooks_block(cfg)["hooks"]["Stop"][0]["hooks"][0]["command"]
        self.assertIn('--path "<SKILL_DIR>/sounds/task-complete/done.wav"', cmd)
        self.assertNotIn("--random", cmd)

    def test_tool_event_gets_matcher(self):
        cfg = an.NotificationConfig(actions=[
            an.Action("pre", "Pre", "PreToolUse", matcher="Bash", sound_mode=an.MODE_RANDOM),
        ])
        self.assertEqual(an.build_hooks_block(cfg)["hooks"]["PreToolUse"][0]["matcher"], "Bash")

    def test_non_tool_event_has_no_matcher(self):
        cfg = an.NotificationConfig()
        cfg.actions[2].sound_mode = an.MODE_RANDOM  # SessionStart
        self.assertNotIn("matcher", an.build_hooks_block(cfg)["hooks"]["SessionStart"][0])


class SkillMdTests(unittest.TestCase):
    def test_frontmatter_and_table(self):
        md = an.build_skill_md(an.NotificationConfig())
        self.assertTrue(md.startswith("---"))
        self.assertIn("name: agent-notifications", md)
        self.assertIn("Sound source", md)

    def test_embeds_valid_hooks_json(self):
        cfg = an.NotificationConfig()
        cfg.actions[0].sound_mode = an.MODE_RANDOM
        md = an.build_skill_md(cfg)
        block = md.split("```json", 1)[1].split("```", 1)[0]
        self.assertIn("Stop", json.loads(block)["hooks"])


class GenerateTests(unittest.TestCase):
    def test_random_copies_all_sounds(self):
        with tempfile.TemporaryDirectory() as base:
            cfg = an.NotificationConfig()
            cfg.ensure_folders(base)
            folder = cfg.actions[0].folder(base)
            _wav(folder, "a.wav")
            _wav(folder, "b.wav")
            cfg.actions[0].sound_mode = an.MODE_RANDOM
            out = os.path.join(base, "skill")
            an.generate_skill(cfg, out, base)
            dest = os.path.join(out, "sounds", "task-complete")
            self.assertEqual(sorted(os.listdir(dest)), ["a.wav", "b.wav"])
            for f in ("SKILL.md", "notifications.json", "play_sound.js"):
                self.assertTrue(os.path.isfile(os.path.join(out, f)))

    def test_single_copies_only_selected(self):
        with tempfile.TemporaryDirectory() as base:
            cfg = an.NotificationConfig()
            cfg.ensure_folders(base)
            folder = cfg.actions[0].folder(base)
            _wav(folder, "a.wav")
            _wav(folder, "b.wav")
            cfg.actions[0].sound_mode = an.MODE_SINGLE
            cfg.actions[0].sound_file = "b.wav"
            out = os.path.join(base, "skill")
            an.generate_skill(cfg, out, base)
            self.assertEqual(os.listdir(os.path.join(out, "sounds", "task-complete")), ["b.wav"])

    def test_random_empty_folder_raises(self):
        with tempfile.TemporaryDirectory() as base:
            cfg = an.NotificationConfig()
            cfg.ensure_folders(base)
            cfg.actions[0].sound_mode = an.MODE_RANDOM  # folder empty
            with self.assertRaises(FileNotFoundError):
                an.generate_skill(cfg, os.path.join(base, "skill"), base)

    def test_single_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as base:
            cfg = an.NotificationConfig()
            cfg.ensure_folders(base)
            cfg.actions[0].sound_mode = an.MODE_SINGLE
            cfg.actions[0].sound_file = "ghost.wav"
            with self.assertRaises(FileNotFoundError):
                an.generate_skill(cfg, os.path.join(base, "skill"), base)

    def test_generate_creates_empty_folders_for_unset_actions(self):
        with tempfile.TemporaryDirectory() as base:
            cfg = an.NotificationConfig()
            cfg.ensure_folders(base)
            out = os.path.join(base, "skill")
            an.generate_skill(cfg, out, base)
            self.assertTrue(os.path.isdir(os.path.join(out, "sounds", "question")))


class InstallSkillTests(unittest.TestCase):
    def test_installs_into_skills_dir_under_skill_name(self):
        with tempfile.TemporaryDirectory() as base:
            cfg = an.NotificationConfig()
            cfg.ensure_folders(base)
            _wav(cfg.actions[0].folder(base), "done.wav")
            cfg.actions[0].sound_mode = an.MODE_RANDOM
            skills = os.path.join(base, "skills")
            path = an.install_skill_global(cfg, base, skills_dir=skills)
            self.assertEqual(path, os.path.join(skills, "agent-notifications"))
            self.assertTrue(os.path.isfile(os.path.join(path, "SKILL.md")))
            self.assertTrue(os.path.isfile(os.path.join(path, "play_sound.js")))

    def test_overwrites_existing_and_drops_stale_files(self):
        with tempfile.TemporaryDirectory() as base:
            cfg = an.NotificationConfig()
            cfg.ensure_folders(base)
            _wav(cfg.actions[0].folder(base), "done.wav")
            cfg.actions[0].sound_mode = an.MODE_RANDOM
            skills = os.path.join(base, "skills")
            path = an.install_skill_global(cfg, base, skills_dir=skills)
            # Plant a stale file that a re-install must not preserve.
            stale = os.path.join(path, "stale.txt")
            with open(stale, "w") as fh:
                fh.write("x")
            an.install_skill_global(cfg, base, skills_dir=skills)
            self.assertFalse(os.path.exists(stale))
            self.assertTrue(os.path.isfile(os.path.join(path, "SKILL.md")))

    def test_validation_error_leaves_existing_install_intact(self):
        with tempfile.TemporaryDirectory() as base:
            cfg = an.NotificationConfig()
            cfg.ensure_folders(base)
            _wav(cfg.actions[0].folder(base), "done.wav")
            cfg.actions[0].sound_mode = an.MODE_RANDOM
            skills = os.path.join(base, "skills")
            path = an.install_skill_global(cfg, base, skills_dir=skills)
            # Now make the config invalid (random action with an empty folder).
            cfg.actions[1].sound_mode = an.MODE_RANDOM  # 'question' folder is empty
            with self.assertRaises(FileNotFoundError):
                an.install_skill_global(cfg, base, skills_dir=skills)
            # Prior install survives.
            self.assertTrue(os.path.isfile(os.path.join(path, "SKILL.md")))


class CliTests(unittest.TestCase):
    def test_set_random_and_generate(self):
        with tempfile.TemporaryDirectory() as base:
            cfg_path = os.path.join(base, "notifications.json")
            # bootstrap folders
            self.assertEqual(an.main(["--config", cfg_path, "list"], base_dir=base), 0)
            _wav(os.path.join(base, "sounds", "task-complete"), "done.wav")
            self.assertEqual(an.main(["--config", cfg_path, "set", "task-complete", "--random"], base_dir=base), 0)
            out = os.path.join(base, "skill")
            self.assertEqual(an.main(["--config", cfg_path, "generate", "--output", out], base_dir=base), 0)
            self.assertTrue(os.path.isfile(os.path.join(out, "SKILL.md")))

    def test_set_file_validates_presence(self):
        with tempfile.TemporaryDirectory() as base:
            cfg_path = os.path.join(base, "notifications.json")
            an.main(["--config", cfg_path, "list"], base_dir=base)
            # no such file -> failure
            self.assertEqual(an.main(["--config", cfg_path, "set", "task-complete", "--file", "x.wav"], base_dir=base), 1)
            _wav(os.path.join(base, "sounds", "task-complete"), "x.wav")
            self.assertEqual(an.main(["--config", cfg_path, "set", "task-complete", "--file", "x.wav"], base_dir=base), 0)

    def test_add_creates_folder(self):
        with tempfile.TemporaryDirectory() as base:
            cfg_path = os.path.join(base, "notifications.json")
            self.assertEqual(
                an.main(["--config", cfg_path, "add", "--id", "sub", "--label", "Sub", "--event", "SubagentStop"], base_dir=base),
                0,
            )
            self.assertTrue(os.path.isdir(os.path.join(base, "sounds", "sub")))
            self.assertIsNotNone(an.NotificationConfig.load(cfg_path).find("sub"))

    def test_implement_installs_to_skills_dir(self):
        with tempfile.TemporaryDirectory() as base:
            cfg_path = os.path.join(base, "notifications.json")
            an.main(["--config", cfg_path, "list"], base_dir=base)
            _wav(os.path.join(base, "sounds", "task-complete"), "done.wav")
            an.main(["--config", cfg_path, "set", "task-complete", "--random"], base_dir=base)
            skills = os.path.join(base, "skills")
            rc = an.main(
                ["--config", cfg_path, "implement", "--skills-dir", skills], base_dir=base
            )
            self.assertEqual(rc, 0)
            self.assertTrue(
                os.path.isfile(os.path.join(skills, "agent-notifications", "SKILL.md"))
            )

    def test_set_unknown_action_fails(self):
        with tempfile.TemporaryDirectory() as base:
            cfg_path = os.path.join(base, "notifications.json")
            self.assertEqual(an.main(["--config", cfg_path, "set", "nope", "--random"], base_dir=base), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
