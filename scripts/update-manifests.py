#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 ParticleG
# SPDX-License-Identifier: 0BSD
"""Generate TwintailLauncher manifests for the Chinese Arknights servers.

Release data comes from the official Hypergryph launcher API. The manifests
only reference the official CDN; this repository never stores game files.
Without --apply nothing is written, and a failure for any server writes nothing.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
APPCODE = "GzD1CpaWgmSq1wew"
RELEASE_URL = "https://launcher.hypergryph.com/api/game/get_latest"
PROXY_URL = "https://launcher.hypergryph.com/api/proxy/web/batch_proxy"
USER_AGENT = "twintail-cn-manifests"
TIMEOUT = 60
# The Arknights icon used by the official arknights_global Twintail manifest.
ICON_URL = "https://cdn2.steamgriddb.com/icon_thumb/7298332f04ac004a0ca44cc69ecf6f6b.png"

_NUMBER = r"(?:0|[1-9][0-9]*)"
VERSION_RE = re.compile(rf"{_NUMBER}(?:\.{_NUMBER})+")
MD5_RE = re.compile(r"[0-9a-f]{32}")
SIZE_RE = re.compile(r"[1-9][0-9]*")

# Launch and compatibility settings follow the official arknights_global manifest.
EXTRA = {
    "fps_unlock_options": ["120"],
    "graphics_api_options": {
        "default": "-force-d3d11",
        "options": [
            {"value": "-force-d3d11", "name": "DirectX 11"},
            {"value": "-force-d3d12", "name": "DirectX 12"},
        ],
    },
    "switches": {"fps_unlocker": False, "jadeite": False, "xxmi": False, "graphics_api": True},
    "compat_overrides": {
        "install_to_prefix": False,
        "disable_protonfixes": True,
        "protonfixes_id": "",
        "protonfixes_store": "",
        "stub_wintrust": False,
        "block_first_req": False,
        "proton_compat_config": ["noxalia"],
        "override_runner": {
            "linux": {"enabled": False, "runner_version": ""},
            "macos": {"enabled": False, "runner_version": ""},
        },
        "min_runner_versions": [],
        "winetricks_verbs": [],
    },
    "steam_import_config": {"enabled": False, "steam_appid_txt": "", "steam_api_dll": ""},
    "preload": {},
}


class ManifestError(Exception):
    pass


@dataclass(frozen=True)
class Server:
    biz: str
    channel: str
    label: str

    @property
    def filename(self) -> str:
        return f"{self.biz}.json"


SERVERS = (
    Server("arknights_cn", "1", "CN Official"),
    Server("arknights_bilibili", "2", "CN Bilibili"),
)


@dataclass(frozen=True)
class Pack:
    url: str
    md5: str
    size: str


@dataclass(frozen=True)
class Release:
    version: str
    res_list_url: str
    packs: tuple[Pack, ...]


@dataclass(frozen=True)
class Background:
    image_url: str
    video_url: str


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _matching(value: object, pattern: re.Pattern[str], what: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ManifestError(f"unexpected {what}: {value!r}")
    return value


def _https_url(value: object, what: str) -> str:
    parts = urllib.parse.urlsplit(value) if isinstance(value, str) else None
    if parts is None or parts.scheme != "https" or not parts.hostname:
        raise ManifestError(f"{what} is not an HTTPS URL: {value!r}")
    return value


def parse_release(data: object) -> Release:
    try:
        version = data["version"]
        pkg = data["pkg"]
        res_list_url = pkg["file_path"]
        packs = tuple(Pack(pack["url"], pack["md5"], pack["package_size"]) for pack in pkg["packs"])
    except (KeyError, TypeError) as error:
        raise ManifestError(f"malformed release response ({type(error).__name__}: {error})") from None
    _matching(version, VERSION_RE, "release version")
    _https_url(res_list_url, "resource list URL")
    if not packs:
        raise ManifestError("release has no packages")
    # Twintail downloads every volume and then extracts from the first URL.
    for index, pack in enumerate(packs, start=1):
        _https_url(pack.url, "package URL")
        _matching(pack.md5, MD5_RE, "package MD5")
        _matching(pack.size, SIZE_RE, "package size")
        name = PurePosixPath(urllib.parse.urlsplit(pack.url).path).name
        if not name.endswith(f".zip.{index:03d}"):
            raise ManifestError(f"package {index} is not volume .zip.{index:03d}: {name}")
    return Release(version, res_list_url, packs)


def parse_background(data: object) -> Background:
    try:
        response = next(item for item in data["proxy_rsps"] if item["kind"] == "get_main_bg_image")
        image = response["get_main_bg_image_rsp"]["main_bg_image"]
        image_url, video_url = image["url"], image.get("video_url") or ""
    except (KeyError, TypeError, AttributeError, StopIteration) as error:
        raise ManifestError(f"malformed background response ({type(error).__name__}: {error})") from None
    _https_url(image_url, "background image URL")
    if video_url:
        _https_url(video_url, "background video URL")
    return Background(image_url, video_url)


def fetch_json(url: str, payload: dict | None = None) -> object:
    headers = {"User-Agent": USER_AGENT}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def fetch_release(server: Server) -> Release:
    query = urllib.parse.urlencode({"appcode": APPCODE, "channel": server.channel, "sub_channel": server.channel})
    return parse_release(fetch_json(f"{RELEASE_URL}?{query}"))


def fetch_background(server: Server) -> Background:
    request = {
        "appcode": APPCODE,
        "language": "zh-cn",
        "channel": server.channel,
        "sub_channel": server.channel,
        "platform": "Windows",
        "source": "launcher",
    }
    payload = {"proxy_reqs": [{"kind": "get_main_bg_image", "get_main_bg_image_req": request}]}
    return parse_background(fetch_json(PROXY_URL, payload))


def version_entry(server: Server, release: Release, background: Background) -> dict:
    return {
        "metadata": {
            "versioned_name": f"Arknights {release.version} ({server.label})",
            "version": release.version,
            "download_mode": "DOWNLOAD_MODE_FILE",
            "game_hash": "",
            "index_file": "",
            "res_list_url": release.res_list_url,
            "diff_list_url": {"game": "", "en_us": "", "zh_cn": "", "ja_jp": "", "ko_kr": ""},
        },
        "assets": {
            "game_icon": ICON_URL,
            "game_background": background.image_url,
            "game_live_background": background.video_url,
        },
        "game": {
            "full": [
                {
                    "file_url": pack.url,
                    "compressed_size": pack.size,
                    "decompressed_size": pack.size,
                    "file_hash": pack.md5,
                    "file_path": "",
                    "region_code": "",
                }
                for pack in release.packs
            ],
            # Twintail applies DOWNLOAD_MODE_FILE patches only for endfield_global and
            # fails updates of any other biz that lists diffs, so updates use the full package.
            "diff": [],
        },
        "audio": {"full": [], "diff": []},
    }


def build_manifest(server: Server, release: Release, background: Background, previous: dict | None) -> dict:
    history = []
    if previous is not None:
        latest = previous["latest_version"]
        if version_key(release.version) < version_key(latest):
            raise ManifestError(f"{server.biz}: refusing downgrade from {latest} to {release.version}")
        # Repairs and downloads look up the installed version, so older entries stay listed.
        history = [entry for entry in previous["game_versions"] if entry["metadata"]["version"] != release.version]
    entry = version_entry(server, release, background)
    return {
        "version": 1,
        "display_name": f"Arknights ({server.label})",
        "biz": server.biz,
        "latest_version": release.version,
        "game_versions": [entry, *history],
        "paths": {
            "audio_pkg_res_dir": "",
            "exe_filename": "Arknights.exe",
            "installation_dir": "",
            "screenshot_dir": "",
            "screenshot_dir_relative_to": "game_dir",
        },
        "assets": entry["assets"],
        "telemetry_hosts": [],
        "extra": EXTRA,
    }


def serialize(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def write_atomic(path: Path, data: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def run(root: Path, apply: bool) -> list[str]:
    """Refresh every manifest and return "<biz> <version>" for each one that changed."""
    updates = []
    for server in SERVERS:
        path = root / server.filename
        current = path.read_text(encoding="utf-8") if path.exists() else None
        previous = None if current is None else json.loads(current)
        release = fetch_release(server)
        text = serialize(build_manifest(server, release, fetch_background(server), previous))
        status = "unchanged" if text == current else "new" if current is None else "updated"
        print(f"{server.biz}: {release.version} ({status})")
        if text != current:
            updates.append((path, text, f"{server.biz} {release.version}"))
    if updates and apply:
        for path, text, _ in updates:
            write_atomic(path, text.encode())
    elif updates:
        print("Dry run: no files written. Re-run with --apply to write the manifests.")
    return [summary for _, _, summary in updates]


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description="Refresh the Arknights CN manifests from the official launcher API.")
    parser.add_argument("--apply", action="store_true", help="write the manifests that changed")
    args = parser.parse_args(argv)
    try:
        changes = run(root, args.apply)
    except (ManifestError, OSError, ValueError, http.client.HTTPException) as error:
        print(f"update-manifests: error: {error}", file=sys.stderr)
        return 1
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"changed={'true' if changes else 'false'}\nsummary={', '.join(changes)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
