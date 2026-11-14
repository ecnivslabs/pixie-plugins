<h1 align="center">Pixie plugins</h1>
<p align="center"><em>The plugin registry for Pixie.</em></p>

This repository is where Pixie finds plugins. The `/plugins` command in Pixie reads a signed list published from here and installs plugins from GitHub releases. Pixie checks every download against the fingerprint recorded in this repository and refuses a file that changed after publication.

## What is here

- **Official plugins.** Made by the Pixie team and reviewed by us. Some are closed source. Pixie can load a relevant one for you when you allow it.
- **Community plugins.** Made by anyone, open source and listed after a short review. Pixie asks you to confirm before installing one and never loads one on its own.
- **A signed list.** `index.json` is rebuilt from the files here and signed, so Pixie can tell it came from this repository and is current.

A plugin runs on your computer with the same access Pixie has. Install community plugins only from people you trust.

## Start here

Open Pixie and run `/plugins`.

- **Discover** lists what is available. Type to search, press Enter on a plugin to read about it, then press `i` to install.
- **Installed** shows what you have and lets you update, pin or remove it.

To list your own plugin, follow [CONTRIBUTING.md](CONTRIBUTING.md). Plugins are written in TypeScript against the `@ecnivslabs/pixie-plugin-api` package, which needs no copy of Pixie to build or test.

## Documentation

- [Contributing](CONTRIBUTING.md): publish a plugin and add it to the registry.
- [Maintaining](MAINTAINING.md): the checks, the signed list, keys and key rotation.

## Reporting problems

Open an issue here with the plugin name and version if a plugin is broken or unsafe. A maintainer can block a version, which makes Pixie switch it off for everyone on its next refresh. Problems in Pixie itself belong in the Pixie project.

## License

The registry files are under the [MIT license](LICENSE). Each plugin has its own license, shown in its details.
