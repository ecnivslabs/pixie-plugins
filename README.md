# Pixie plugins

This is where Pixie finds plugins. When you run `/plugins` inside Pixie, the list you see comes from here.

## Use a plugin

Open Pixie and type `/plugins`.

- **Discover** lists what is available. Type to search, press Enter on a plugin to see what it does, then press `i` to install it.
- **Installed** shows what you have, and lets you update, pin or remove it.

Every download is checked against a fingerprint saved in this repository, so Pixie refuses a file that was changed after it was published.

Plugins come in two kinds:

| Kind | Made by | What to know |
|---|---|---|
| Official | The Pixie team | Reviewed by us. Some are closed source. Pixie can load a relevant one for you when you allow it. |
| Community | Anyone | Open source and listed after a short review. Pixie asks you to confirm before installing, and never loads one on its own. |

A plugin runs on your computer with the same access Pixie has. Install community plugins the way you would install any program: only from people you trust.

## Make a plugin

Anyone can list a plugin. The steps are in [CONTRIBUTING.md](CONTRIBUTING.md): write the plugin, publish it as a release on GitHub, then open a pull request here with one small file change.

Plugins can be written in TypeScript against the published `@ecnivslabs/pixie-plugin-api` package. You do not need a copy of Pixie to build or test one.

## Report a problem

- A plugin is broken or unsafe: open an issue here with the plugin name and version. We can pull a version so Pixie switches it off for everyone.
- Pixie itself is misbehaving: tell us in the Pixie project instead.

## For maintainers

How the signed list is built, how keys are handled and how reviews work is in [MAINTAINING.md](MAINTAINING.md).

## License

The registry files are under the [MIT license](LICENSE). Each plugin has its own license, shown in its details.
