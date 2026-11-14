# Contributing to the Pixie plugin registry

The registry lists plugins for Pixie. Contributions add a plugin, publish a new version of one, or improve the checks and documentation. Plugin changes go through a pull request that touches exactly one plugin.

## Before listing a plugin

The plugin must live in a public GitHub repository you can write to, and it must be open source under a license that lets people use it, such as MIT or Apache-2.0. Names starting with `official`, `pixie` or `ecnivs` are reserved for the Pixie team.

If the plugin sends data off the machine, its description must say so. Plugins that hide what they do, or try to get around Pixie's checks, are removed.

## Writing the plugin

Install the types package so your editor knows what Pixie provides:

```sh
bun add -d @ecnivslabs/pixie-plugin-api
```

Its README covers the TypeScript setup and how to test a plugin against a real Pixie host without installing Pixie.

`package.json` needs `version`, `engines.pixie` (the Pixie versions you support, for example `>=1.0.17 <2.0.0`) and `pixie.plugin` (the file that starts the plugin).

## Publishing a release

Pack the plugin as `<name>-<version>.tar.gz` with `package.json` at the top of the archive. Create a GitHub release tagged `<name>-<version>` and upload the archive to it.

## Opening the pull request

Fork this repository. From a checkout of your fork, with the [GitHub CLI](https://cli.github.com) signed in, run:

```sh
python3 tools/make_record.py <owner/repo> <release tag> <name>-<version>.tar.gz <name>
```

The tool reads your release, downloads the files and prints the line to add.

**A new plugin** adds three files:

- `index/<first two letters of the name>/<name>`: the printed line.
- `owners/<name>.json`: `{"repository_id": 123, "repository": "owner/repo"}`. Get the number with `gh api repos/<owner>/<repo> --jq .id`.
- `meta/<name>.json`: the title, a one line summary, search keywords, license, source link and what the plugin adds. `meta/video.json` shows the shape. Set `"tier": "community"`.

Write the summary for the model as well as for people. Pixie shows it to the model, which uses it to decide whether the plugin fits a task. Say what the plugin does, then when to use it, with the main use first, in 280 characters or fewer. A vague summary makes the plugin load when it should not, or not load when it should.

**A new version** appends one line to the plugin's file in `index/` and changes nothing else.

## Review

An automatic check reads your release files and confirms you own the repository. It never runs your code. If it fails, the comment on the pull request says what to fix.

A new plugin then waits for a maintainer, who reads what it does, whether the description is true and whether anything looks unsafe. A new version of an accepted plugin is merged once the check passes, and appears in Pixie after the next rebuild of the signed list.

## Changing or removing a version

Publish a fix as a new release with a new line. To stop new installs of a version, open an issue asking for it to be yanked; existing installs keep working. A dangerous version can be blocked, which makes Pixie switch it off on its next refresh. To remove a plugin entirely, open an issue.

## Verification

Run the registry tests before changing anything under `.github/scripts` or `tools`:

```sh
python3 -I -m unittest discover -s tests -p 'test_*.py' -v
```
