#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 ParticleG
# SPDX-License-Identifier: 0BSD

import contextlib
import importlib.util
from importlib.machinery import SourceFileLoader
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import urllib.parse

PROJECT = Path(__file__).resolve().parent.parent


def load_generator():
    loader = SourceFileLoader("update_manifests", str(PROJECT / "scripts" / "update-manifests.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


generator = load_generator()

# Mirrors the serde models TwintailLauncher deserializes manifests into
# (src-tauri/src/utils/models.rs). A missing field makes Twintail panic on load.
FULL_GAME_FILE = {
    "file_url": str,
    "compressed_size": str,
    "decompressed_size": str,
    "file_hash": str,
    "file_path": str,
    "region_code": str,
}
DIFF_GAME_FILE = {
    "file_url": str,
    "compressed_size": str,
    "decompressed_size": str,
    "file_hash": str,
    "file_path": str,
    "diff_type": str,
    "original_version": str,
    "delete_files": [str],
}
ASSETS = {"game_icon": str, "game_background": str, "game_live_background": str}
GAME_VERSION = {
    "metadata": {
        "versioned_name": str,
        "version": str,
        "download_mode": str,
        "game_hash": str,
        "index_file": str,
        "res_list_url": str,
        "diff_list_url": {"game": str, "en_us": str, "zh_cn": str, "ja_jp": str, "ko_kr": str},
    },
    "assets": ASSETS,
    "game": {"full": [FULL_GAME_FILE], "diff": [DIFF_GAME_FILE]},
    "audio": {"full": [dict], "diff": [dict]},
}
RUNNER_OVERRIDE = {"enabled": bool, "runner_version": str}
GAME_MANIFEST = {
    "version": int,
    "display_name": str,
    "biz": str,
    "latest_version": str,
    "game_versions": [GAME_VERSION],
    "telemetry_hosts": [str],
    "paths": {
        "audio_pkg_res_dir": str,
        "exe_filename": str,
        "installation_dir": str,
        "screenshot_dir": str,
        "screenshot_dir_relative_to": str,
    },
    "assets": ASSETS,
    "extra": {
        "preload": dict,
        "switches": {"fps_unlocker": bool, "jadeite": bool, "xxmi": bool, "graphics_api": bool},
        "compat_overrides": {
            "install_to_prefix": bool,
            "disable_protonfixes": bool,
            "protonfixes_id": str,
            "protonfixes_store": str,
            "stub_wintrust": bool,
            "block_first_req": bool,
            "proton_compat_config": [str],
            "override_runner": {"linux": RUNNER_OVERRIDE, "macos": RUNNER_OVERRIDE},
            "min_runner_versions": [str],
            "winetricks_verbs": [str],
        },
        "fps_unlock_options": [str],
        "steam_import_config": {"enabled": bool, "steam_appid_txt": str, "steam_api_dll": str},
        "graphics_api_options": {"options": [{"value": str, "name": str}], "default": str},
    },
}


def assert_shape(test, value, schema, path="manifest"):
    if isinstance(schema, dict):
        test.assertIsInstance(value, dict, path)
        test.assertEqual(set(value), set(schema), path)
        for key, child in schema.items():
            assert_shape(test, value[key], child, f"{path}.{key}")
    elif isinstance(schema, list):
        test.assertIsInstance(value, list, path)
        for index, item in enumerate(value):
            assert_shape(test, item, schema[0], f"{path}[{index}]")
    else:
        test.assertIs(type(value), schema, path)


def release(version, channel, volumes=2):
    base = f"https://ak.hycdn.cn/{generator.APPCODE}/update/{channel}/{channel}/Windows/{version}_fixture"
    packs = [
        {"url": f"{base}/packs/game.zip.{index:03d}", "md5": f"{index:032x}", "package_size": str(1000 + index)}
        for index in range(1, volumes + 1)
    ]
    return {"version": version, "pkg": {"file_path": f"{base}/files", "packs": packs}}


def background(channel):
    image = {"url": f"https://img.example.invalid/{channel}.png", "video_url": ""}
    return {"proxy_rsps": [{"kind": "get_main_bg_image", "get_main_bg_image_rsp": {"main_bg_image": image}}]}


class GeneratorTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.releases = {"1": release("79.0.0", "1"), "2": release("79.0.0", "2")}
        patcher = mock.patch.object(generator, "fetch_json", side_effect=self.fake_fetch)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_fetch(self, url, payload=None):
        if payload is None:
            self.assertTrue(url.startswith(generator.RELEASE_URL + "?"))
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            self.assertEqual(query["channel"], query["sub_channel"])
            return self.releases[query["channel"][0]]
        self.assertEqual(url, generator.PROXY_URL)
        return background(payload["proxy_reqs"][0]["get_main_bg_image_req"]["channel"])

    def run_generator(self, *args):
        output = self.root / "github-output"
        output.write_text("")
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = generator.main(list(args), root=self.root)
        return code, stdout.getvalue(), stderr.getvalue(), output.read_text()

    def manifest(self, biz):
        return json.loads((self.root / f"{biz}.json").read_text())

    def snapshot(self):
        return {path.name: path.read_bytes() for path in self.root.glob("*.json")}

    def test_writes_twintail_compatible_manifests(self):
        code, stdout, _, output = self.run_generator("--apply")

        self.assertEqual(code, 0)
        self.assertIn("changed=true", output)
        self.assertIn("summary=arknights_cn 79.0.0, arknights_bilibili 79.0.0", output)
        for server in generator.SERVERS:
            with self.subTest(server=server.biz):
                manifest = self.manifest(server.biz)
                assert_shape(self, manifest, GAME_MANIFEST)
                self.assertEqual(manifest["biz"], server.biz)
                self.assertEqual(manifest["latest_version"], "79.0.0")
                [entry] = manifest["game_versions"]
                self.assertEqual(entry["metadata"]["download_mode"], "DOWNLOAD_MODE_FILE")
                self.assertEqual(entry["metadata"]["res_list_url"], self.releases[server.channel]["pkg"]["file_path"])
                self.assertEqual(entry["assets"]["game_background"], f"https://img.example.invalid/{server.channel}.png")
                self.assertEqual(
                    [(file["file_url"], file["file_hash"], file["compressed_size"]) for file in entry["game"]["full"]],
                    [(pack["url"], pack["md5"], pack["package_size"]) for pack in self.releases[server.channel]["pkg"]["packs"]],
                )
                self.assertEqual(entry["game"]["diff"], [])

    def test_dry_run_writes_nothing(self):
        code, stdout, _, output = self.run_generator()

        self.assertEqual(code, 0)
        self.assertIn("Dry run", stdout)
        self.assertIn("changed=true", output)
        self.assertEqual(self.snapshot(), {})

    def test_new_release_keeps_installed_versions_listed(self):
        self.releases = {"1": release("78.0.0", "1"), "2": release("78.0.0", "2")}
        self.assertEqual(self.run_generator("--apply")[0], 0)
        self.releases["1"] = release("79.0.0", "1", volumes=3)

        code, stdout, _, output = self.run_generator("--apply")

        self.assertEqual(code, 0)
        self.assertIn("summary=arknights_cn 79.0.0\n", output)
        self.assertIn("arknights_bilibili: 78.0.0 (unchanged)", stdout)
        versions = [entry["metadata"]["version"] for entry in self.manifest("arknights_cn")["game_versions"]]
        self.assertEqual(versions, ["79.0.0", "78.0.0"])
        self.assertEqual(len(self.manifest("arknights_cn")["game_versions"][0]["game"]["full"]), 3)

        before = self.snapshot()
        code, _, _, output = self.run_generator("--apply")
        self.assertEqual(code, 0)
        self.assertIn("changed=false", output)
        self.assertEqual(self.snapshot(), before)

    def test_refused_downgrade_writes_no_manifest(self):
        self.assertEqual(self.run_generator("--apply")[0], 0)
        before = self.snapshot()
        self.releases = {"1": release("78.0.0", "1"), "2": release("80.0.0", "2")}

        code, _, stderr, output = self.run_generator("--apply")

        self.assertEqual(code, 1)
        self.assertIn("refusing downgrade from 79.0.0 to 78.0.0", stderr)
        self.assertEqual(output, "")
        self.assertEqual(self.snapshot(), before)

    def test_malformed_release_writes_no_manifest(self):
        def broken(change):
            data = release("79.0.0", "2")
            change(data)
            return data

        cases = {
            "bad md5": lambda data: data["pkg"]["packs"][0].update(md5="not-a-hash"),
            "plain http": lambda data: data["pkg"]["packs"][1].update(url=data["pkg"]["packs"][1]["url"].replace("https:", "http:")),
            "no packages": lambda data: data["pkg"].update(packs=[]),
            "volumes out of order": lambda data: data["pkg"]["packs"].reverse(),
            "bad version": lambda data: data.update(version="latest"),
            "missing pkg": lambda data: data.pop("pkg"),
        }
        for name, change in cases.items():
            with self.subTest(name):
                self.releases["2"] = broken(change)

                code, _, stderr, _ = self.run_generator("--apply")

                self.assertEqual(code, 1)
                self.assertIn("update-manifests: error:", stderr)
                self.assertEqual(self.snapshot(), {})

    def test_repository_lists_every_committed_manifest(self):
        repository = json.loads((PROJECT / "repository.json").read_text())

        self.assertEqual(repository["manifests"], [server.filename for server in generator.SERVERS])
        for server in generator.SERVERS:
            with self.subTest(server=server.biz):
                manifest = json.loads((PROJECT / server.filename).read_text())
                assert_shape(self, manifest, GAME_MANIFEST)
                self.assertEqual(manifest["biz"], server.biz)


if __name__ == "__main__":
    unittest.main()
