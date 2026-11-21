# twintail-cn-manifests

Third-party [TwintailLauncher](https://github.com/TwintailTeam/TwintailLauncher)
game manifests for the Chinese Arknights servers:

| Manifest | Server | `biz` |
|---|---|---|
| `arknights_cn.json` | CN Official (Hypergryph) | `arknights_cn` |
| `arknights_bilibili.json` | CN Bilibili | `arknights_bilibili` |

TwintailTeam does not plan to support Chinese game clients, so this repository
is maintained separately. Report problems with these manifests here, not to
TwintailTeam.

## Status

Stock TwintailLauncher 2.5.3 cannot use third-party game repositories yet:

- No screen calls the backend's `add_repository` command, so a repository
  cannot be added from the launcher.
- The "update third-party repositories" setting is stored but never read, so
  added repositories are never fetched again.
- With a second game repository present, building the game list throws a
  `TypeError` in the frontend and no games are listed, official ones included.

With these issues worked around, `arknights_cn` 79.0.0 was installed and
launched with TwintailLauncher 2.5.3 and `11.0-20261015-proton-cachyos`: all
14,021 files matched the package CRCs, and the game finished its in-game
resource update and reached the voice pack selection. `arknights_bilibili`
uses the same package format.

Repository URL:

```
https://github.com/ParticleG/twintail-cn-manifests.git
```

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

- **Updates download the full package.** TwintailLauncher applies
  `DOWNLOAD_MODE_FILE` differential patches only for `endfield_global` and
  marks updates of any other game that lists patches as failed. The manifests
  therefore list no patches, and each client update downloads the full package
  (about 22 GB) and needs about 48 GB of free space while it is extracted.
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
