# twintail-cn-manifests

Third-party [TwintailLauncher](https://github.com/TwintailTeam/TwintailLauncher)
game manifests for the Chinese Arknights servers:

| Manifest | Server | `biz` |
|---|---|---|
| `arknights_cn.json` | CN Official (Hypergryph) | `arknights_cn` |
| `arknights_bilibili.json` | CN Bilibili | `arknights_bilibili` |

TwintailLauncher 2.x does not support Chinese game clients. Its maintainer has
said that 3.0 will
([TwintailTeam/TwintailLauncher#379](https://github.com/TwintailTeam/TwintailLauncher/issues/379));
until then this repository is maintained separately, and it will stop being
maintained once the official launcher supports these servers. Report problems
with these manifests here, not to TwintailTeam.

## Usage

Stock TwintailLauncher 2.5.3 cannot use third-party game repositories: it has
no way to add one, never updates them, and lists no games at all once a second
game repository exists
([TwintailTeam/TwintailLauncher#379](https://github.com/TwintailTeam/TwintailLauncher/issues/379)).
Use [TwintailLauncher-CN](https://github.com/ParticleG/TwintailLauncher-CN),
a fork that carries only the fixes for these issues:

1. Install `twintaillauncher-cn` from the AUR, or build the fork.
2. Open **Repositories** in the sidebar, choose **+**, and enter
   `ParticleG/twintail-cn-manifests`.
3. In **Settings → General**, turn on **Auto-update 3rd Party Repos** so new
   game versions are fetched when the launcher starts.

`arknights_cn` 79.0.0 was installed and launched with TwintailLauncher 2.5.3
and `11.0-20261015-proton-cachyos`: all 14,021 files matched the package
CRCs, and the game finished its in-game resource update and reached the voice
pack selection. `arknights_bilibili` uses the same package format.

## How the manifests are built

`scripts/update-manifests.py` queries the official Hypergryph launcher API
(`launcher.hypergryph.com`, channels `1` and `2`) and writes one manifest per
server. The manifests only link to the official CDN; this repository contains
no game files. A GitHub Actions workflow refreshes them every two hours and
commits changes to `main`.

The generator refuses version downgrades and writes nothing if any server
returns unexpected data. Older versions stay listed so repairs of installs
that have not been updated yet keep working.

## Limitations

- **Updates download the full package.** Stock TwintailLauncher applies
  `DOWNLOAD_MODE_FILE` differential patches only for `endfield_global` and
  marks updates of any other game that lists patches as failed. The fork
  selects patches by `diff_type`, but Arknights CN patches have not been
  tested with it yet, so the manifests list no patches. Each client update
  downloads the full package (about 22 GB) and needs about 48 GB of free
  space while it is extracted.
- Repairs also download the full package.
- Launch and compatibility settings are copied from the official
  `arknights_global` manifest.

## Development

```sh
python3 -m unittest discover -s tests -v
python3 scripts/update-manifests.py          # dry run
python3 scripts/update-manifests.py --apply  # write changed manifests
```

## License

The generator and tests are licensed under the [0BSD](LICENSE) license.
Arknights and its assets belong to Hypergryph. This project is not affiliated
with Hypergryph, Bilibili, or TwintailTeam.
