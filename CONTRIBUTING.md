# Add a plugin to the registry

Thanks for building something for Pixie. This page walks through getting a plugin listed and keeping it up to date.

## Before you start

- The plugin lives in your own public GitHub repository.
- It is open source, under a license that lets people use it (MIT, Apache-2.0 and similar).
- You have write access to that repository.
- Its name is not taken and does not start with `official`, `pixie` or `ecnivs`. Those are kept for the Pixie team.

## Write the plugin

Use the types package so your editor knows what Pixie offers:

```sh
bun add -d @ecnivslabs/pixie-plugin-api
```

Its README explains how to set up TypeScript and how to test your plugin against a real Pixie host without installing Pixie.

Your `package.json` needs three things:

- `version`, for example `1.0.0`.
- `engines.pixie`, the Pixie versions you support, for example `>=1.0.17 <2.0.0`.
- `pixie.plugin`, pointing at the file that starts your plugin.

Keep it honest: if your plugin sends anything off the machine, say so in its description.

## Publish a release

1. Build your plugin and pack it as a `.tar.gz` named `<name>-<version>.tar.gz`. `package.json` must sit at the top of the archive.
2. On GitHub, create a release with a tag such as `<name>-<version>` and upload the archive as a release file.

## Open a pull request here

Fork this repository, then run this from a checkout of your fork. It reads your release, downloads the files and writes the lines you need:

```sh
python3 tools/make_record.py <your-user>/<your-repo> <release tag> <name>-<version>.tar.gz <name>
```

You need the [GitHub CLI](https://cli.github.com) signed in. It prints one line. Then:

**For a new plugin**, add three files:

- `index/<first two letters of the name>/<name>`: the line the tool printed.
- `owners/<name>.json`: `{"repository_id": 123, "repository": "your-user/your-repo"}`. The number is your repository's ID (`gh api repos/<user>/<repo> --jq .id`).
- `meta/<name>.json`: the title, a one line summary, search keywords, your license, a link to your source, and what the plugin adds. Look at `meta/video.json` for the shape, and set `"tier": "community"`.

**For a new version**, add one line to the end of your plugin's file in `index/` and change nothing else.

Change only one plugin per pull request.

## What happens next

An automatic check looks at your release files and confirms you own the repository. It never runs your code.

- A new plugin then waits for a person to read it. We look at what the plugin does, whether the description is true, and whether anything looks unsafe.
- A new version of a plugin we have already accepted is merged by itself once the check passes and appears in Pixie after the registry list is rebuilt.

If the check fails, the comment on your pull request says what to fix.

## Updating, pulling and removing

- To ship a fix, publish a new release and add a new line as above.
- To stop people getting a version, open an issue asking us to yank it. Existing installs keep working; new installs skip it.
- If a version is dangerous, say so in an issue. We can block it, which makes Pixie switch it off for everyone on its next refresh.
- To remove your plugin entirely, open an issue.

## Run the checks yourself

```sh
python3 -I -m unittest discover -s tests -p 'test_*.py' -v
```

## Conduct

Be kind and be straight. Plugins that hide what they do, collect data without saying so or try to get around Pixie's checks will be removed.
