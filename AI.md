# Repository knowledge

Read the relevant specifications in `~/Files/workspace/specs` before working.
Keep durable repository knowledge here and only unfinished checkpoints in `TODO.md`.
Work in reviewable steps, preserve user edits, and do not commit automatically.
For deployment or Workshop publication, supply commands unless execution is requested.
`TODO.md` is owner-managed and should not be committed automatically.

## Assets and naming

`games/<game-slug>/` contains hosted assets. The production base URL is
`https://assets.tabtop.wynd.is/`; repository paths map directly to URL paths.
`https://bgdb.yin.ong/` is the previous host.

Use lowercase ASCII slug components with hyphens, preserving file extensions.
`README.md` and `LICENSE` are conventional documentation exceptions. Use `en` and
`zh` for language-specific assets, and `shared` for language-independent assets.
Use meaningful directory groups, such as `leaders/<country>/<name>`, and omit
filename prefixes already expressed by their directories. Separate numeric variant
suffixes with a hyphen. Keep full faction names where used; Clash of Sovereigns
intentionally retains its two-letter deck codes.

Current layouts:

- The Napoleonic Wars: `shared/{flags,models,music,room,decks}` and
  `shared/thumbnail.jpg`; `en/docs/rules-2008.pdf`;
  `zh/{boards,decks,docs,hq-displays,squadrons}`,
  `zh/leaders/front/<country>/<name>.png`, `zh/leaders/back/<country>.png`,
  and `zh/markers/{event,game}`. HQ displays use `<country>[-n].png`;
  flags and squadrons use `<country>.png`.
- Clash of Sovereigns: `shared/room/table.png`;
  `zh/decks/{au,br,fr,pr}.png`, `zh/docs/rules.pdf`;
  `en/boards/played-events-checklist.png` and `en/rules.pdf` remain in place.
- Tanto Monta: `shared/deck/events-back.jpg` (singular `deck`),
  `shared/identity/{box-1,box-2,icon}.jpg`,
  `shared/identity/gmt-games-logo.png`, `shared/room/table.jpg`;
  `en/docs/rules.pdf`; `zh/boards`, `zh/boards/player-cards/<country>.png`,
  `zh/decks/{events-1,events-2,home}.png`, `zh/leaders/<country>/<name>.png`,
  `zh/naos/<country>/<name>-n.png`, and `zh/docs/rules.pdf`.

The three games contain 177 assets (112 Napoleonic Wars, 8 Clash of Sovereigns,
57 Tanto Monta), plus six README/license files. Filename audits and local URL
validation passed. Renames preserved asset bytes and changed only URLs in module
JSON, including URLs embedded in Lua and saved configuration. Third-party asset
hosts remain unchanged. These local checks do not establish deployment status.

## Asset deployment

`.github/workflows/deploy.yaml` runs on pushes to `main` and manual dispatch.
`scripts/deploy.py` reads committed `games/` files from Git HEAD, compares checksums
with Bunny Storage's `/_deploy/manifest.json`, uploads changes, and deletes removed
paths. Git LFS covers JPG, PNG, PDF, OBJ, and MP3 files. CI skips checkout smudging
and downloads LFS content only for changed assets.

The upload job saves successful operations in a `result.json` artifact and updates
the manifest. The purge job downloads that artifact and purges successful changes
through Bunny's API. Failures are reported so reruns can continue remaining work.
Configuration uses `BUNNY_STORAGE_ENDPOINT` and `BUNNY_PULL_ZONE_HOSTNAME` variables,
and `BUNNY_STORAGE_PASSWORD` and `BUNNY_API_KEY` secrets. No pull-zone ID is needed.

Local assets are checked for lowercase slug directories and filenames with lowercase
alphanumeric extensions before their Git blobs are read. README.md and LICENSE are
allowed only directly under games/<game-slug>/. Remote manifests and cleanup retain
path-safety validation so legacy filenames can still be removed. A rename is an
upload plus deletion; there is no automatic redirect or old-path alias.
Deploy and verify new URLs before publishing module JSON that references them.
Rollback requires restoring the matching asset paths and module JSON together,
then deploying and republishing as appropriate.

## TTS modules and local publishing

`tts-workshop/<slug>/` contains `<workshop-id>.json`, its thumbnail, and a README
with the module name. There are 13 modules; the JSON filename supplies the Workshop
ID. The principal migrated modules and the test item are:

| Slug | Workshop ID |
| --- | --- |
| the-napoleonic-wars | 2243324560 |
| clash-of-sovereigns | 3332432605 |
| tanto-monta | 3109618169 |
| test | 3826709471 |

Run `mise tts-update <game-slug>` with Steam running and logged in.
`scripts/tts-update.py` encodes the JSON as temporary BSON and calls
`steam-workshop update-file 286160 <item-id> <temporary-bson>`.
It updates content only; the thumbnail is unchanged. Temporary files are cleaned
up and upload failures propagate. The script uses inline uv dependencies and
`scripts/tts-update.py.lock`; there is intentionally no Python project or repository
virtual environment. `bson` comes from PyMongo, with a targeted Pyright missing-import
suppression for the isolated script environment.

Mise manages Python, uv, and `github:isonovio/steam-workshop@latest`. The Rust CLI
lives in `~/Files/workspace/projects/steam-workshop`; it replaces the earlier
KP-Steam experiment. The macOS ARM64 release includes its Steam library.

JSON/BSON round trips passed for all 13 modules. The Rust publisher's private-item
upload/download and TTS loading were verified, and the user confirmed the Python
task worked for Clash of Sovereigns. Latest directory reorganizations still need
the deployment/publication checks listed in `TODO.md`.
