# pixie-plugins

Plugin registry for [Pixie](https://github.com/ecnivslabs/pixie). Pixie downloads a signed `index.json` from this repository's GitHub Pages site and installs plugins from GitHub release assets, verifying every download against the hash recorded here.

## Tiers

| Tier | Who | Review | Autoload |
|---|---|---|---|
| `official` | Accounts listed in `official-owners.json` (vinceswu, ecnivslabs). May be closed source. | Maintainers | Yes, when the user enables it |
| `community` | Anyone with write access to a public plugin repository. Must be open source. | Maintainer review for each new plugin, automatic merge for new versions of a reviewed plugin | Never. Installed only after the user confirms. |

Names starting with `official`, `pixie` or `ecnivs` are reserved for official plugins.

## Layout

| Path | Contents |
|---|---|
| `index/<2 chars>/<name>` | One JSON object per line, one line per published version. Append only. |
| `meta/<name>.json` | Tier, title, summary, keywords, license, source, relevance signals, components. `relevance.cwd` and `relevance.filesRead` are globs matched locally against files in the user's project; `relevance.manifestDeps` names are matched against its `package.json` dependencies. |
| `owners/<name>.json` | `{"repository_id": 123, "repository": "owner/name"}`. The numeric ID is authoritative. |
| `official-owners.json` | Numeric GitHub account IDs allowed to publish official plugins. |
| `blocklist.json` | `{name, vers, reason}` entries that Pixie disables on the next index refresh. `vers` is an exact version. |
| `registry-signing.public.pem` | Ed25519 public key that verifies `index.json`. |

### Version record

```json
{"name":"video","vers":"1.0.0","engines":{"pixie":">=1.0.17 <2.0.0"},"dl":"https://github.com/ecnivslabs/pixie-plugins-dist/releases/download/video-1.0.0/video-1.0.0.tar.gz","sha256":"<64 lowercase hex>","size":1048576,"published_at":"2026-11-01T10:00:00Z","yanked":false}
```

- `engines.pixie` uses the grammar Pixie enforces for `package.json` (`>=`, `<=`, `>`, `<`, `=`, `^`, `~` comparators of full `MAJOR.MINOR.PATCH`, separated by spaces).
- `dl` must be an uploaded asset of a published GitHub release in the bound repository and must end in `.tar.gz` (at most 64 MiB).
- `published_at` must equal the release asset's creation time. Pixie waits two hours after this time before auto-updating to a version, and CI rejects any other value.
- `native` (optional) maps `linux-x64`, `linux-arm64`, `darwin-x64`, `darwin-arm64`, `win32-x64` and `win32-arm64` to `{url, sha256, size}` for per-platform binaries (at most 256 MiB each).
- `yanked` is `false` when published. A maintainer sets it to `true` by hand; automation never edits existing lines.

## Publishing

Create the version record from a release instead of computing hashes by hand:

```sh
python3 tools/make_record.py <owner/repo> <release tag> <name>-<version>.tar.gz <name>
```

It reads the release through `gh`, downloads the archive, checks the record against the same rules CI applies and prints one line to append to `index/<2 chars>/<name>`.

Open a pull request that changes exactly one plugin.

- **New plugin:** add `index/<2 chars>/<name>` (one line), `meta/<name>.json` and `owners/<name>.json`. CI verifies the release assets and your permission, then labels the PR `manual-review`. A maintainer decides.
- **New version:** append one line to the plugin's index file and change nothing else. CI squash-merges it once everything verifies, then publishes a new signed index.

`.github/workflows/validate.yml` runs from the base branch on `pull_request_target`. It reads the pull request as git objects and never runs submitted code. For every submission it checks that:

1. exactly one plugin changes, existing bytes are preserved and files are regular, non-executable and under 1 MiB;
2. JSON is strict (no duplicate keys or `NaN`) and every field passes the schema in `.github/scripts/registry.py`;
3. each asset URL is an uploaded asset of a published release in the repository bound by ID in `owners/`, and its size and SHA-256 match after download over HTTPS (redirects off HTTPS are refused);
4. the PR author owns the repository or has `write` or `admin` permission on it (`maintain` counts as `write`), checked before and after the downloads;
5. for `official` plugins, the repository owner's numeric ID is in `official-owners.json`;
6. the archive is a readable `.tar.gz` of plain relative paths holding only regular files and directories (no links, devices, `..` or absolute names, at most 20,000 entries and 512 MiB expanded), with a root `package.json` whose `pixie.plugin`, `version` and `engines.pixie` agree with the record. Entries are streamed and never extracted. Pixie repeats these checks when it installs.

Closed-source official plugins keep their source in a private repository and publish compiled archives as release assets of a public distribution repository (`ecnivslabs/pixie-plugins-dist`), which is the repository bound in `owners/`. GitHub release assets inherit repository visibility, so a private repository cannot serve anonymous downloads.

Pull requests that touch anything else (metadata, owners, blocklist, workflows) get no automation and need a maintainer.

## Signed index

`.github/workflows/publish.yml` builds `index.json` and signs its exact bytes with Ed25519, writing `index.json.sig` (base64). The document carries:

- `version`: Unix time of generation. Clients refuse an index older than the newest one they have seen.
- `expires`: seven days after generation. Clients refuse an expired index for new installs. A daily scheduled run re-signs it so a quiet registry does not expire.
- `plugins`: per plugin, its meta and all version records.
- `blocklist`.

The signing key lives only in the `registry-signing` environment secret `REGISTRY_SIGNING_KEY`. It is separate from Pixie's application release key, so a registry compromise cannot sign app updates.

### One-time setup

```sh
openssl genpkey -algorithm ed25519 -out registry-signing.pem
openssl pkey -in registry-signing.pem -pubout -out registry-signing.public.pem
```

Commit `registry-signing.public.pem`. Store the private key as the `REGISTRY_SIGNING_KEY` secret of a `registry-signing` environment restricted to `master`, then delete the local private key or move it to offline backup. Enable GitHub Pages with source "GitHub Actions". Add a `REGISTRY_OWNERSHIP_TOKEN` secret (fine-grained token with read access to repository collaborators for the plugin repositories) so permission checks work for organization repositories. Protect `master` so only maintainers merge changes outside the automated flow.

Key rotation: ship a Pixie release that trusts both the old and the new public key, switch signing to the new key, then ship a release that drops the old one. A compromised key needs a Pixie release that replaces the pinned public key and an index signed with the new key.

## Tests

```sh
python3 -I -m unittest discover -s tests -p 'test_*.py' -v
```

## Design basis

- Append-only per-plugin files, ownership bound to the repository ID, validation without executing submissions and the release-asset checks follow the [Olive pit registry](https://github.com/ecnivslabs/pit-registry).
- Signed, expiring, monotonically versioned metadata defends against rollback and freeze attacks as described in the [TUF specification](https://theupdateframework.github.io/specification/latest/).
- Tiers, reserved names, SHA-pinned archive sources and never auto-installing community plugins follow [Claude Code's plugin marketplaces](https://code.claude.com/docs/en/plugins/anthropic-marketplaces).
- The two-hour wait before auto-updating a new version follows [VS Code's extension update delay](https://infoq.com/news/2026/06/vscode-extension-update-delay).
- Workflow actions are pinned to commit SHAs, as GitHub's [security hardening guide](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions#using-third-party-actions) recommends.
- Build provenance attestations are not used: GitHub offers them for private repositories only on Enterprise Cloud, so closed-source plugins rely on the signed index and recorded hash.
