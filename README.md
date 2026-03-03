# KodiDevKit

[![License](https://img.shields.io/badge/License-GPL%20v3%2B-blue.svg)](https://raw.githubusercontent.com/MikeSiLVO/KodiDevKit/master/LICENSE)
[![Sublime Text](https://img.shields.io/badge/Sublime%20Text-4-orange.svg)](https://www.sublimetext.com/)

A Sublime Text 4 plugin for Kodi skin and addon development. Provides validation, intelligent tooltips, auto-completion, JSON-RPC integration, and more.

## Documentation

- [**Validation**](docs/validation.md) -- On-save XML checks and full-skin reports covering variables, includes, labels, fonts, IDs, images, and XML structure.
- [**Features**](docs/features.md) -- Tooltips, auto-completion, keyboard shortcuts, fuzzy searches, context menu, JSON-RPC commands, Kodi log integration.
- [**Settings**](docs/settings.md) -- Every setting with type, default, and description.
- [**Skin Shortcuts**](docs/skinshortcuts.md) -- How KodiDevKit handles runtime-generated content from script.skinshortcuts.

## Requirements

1. **Sublime Text 4** or later.
2. **Project structure**: Open your Kodi addon root as the only project folder.
3. **Configuration**: Set up KodiDevKit settings via Preferences > Package Settings > KodiDevKit. At minimum, set `kodi_path` to your Kodi installation folder.

## Installation

Clone into your Sublime Text `Packages` folder:

```bash
# Windows
cd "~/AppData/Roaming/Sublime Text/Packages"

# macOS
cd "~/Library/Application Support/Sublime Text/Packages"

# Linux
cd "~/.config/sublime-text/Packages"

git clone https://github.com/MikeSiLVO/KodiDevKit.git
```

Restart Sublime Text after cloning.

*Note: The Package Control listing still points to the [original repository](https://github.com/phil65/KodiDevKit), which is no longer maintained. Install via git clone above to get the current version.*

## License

[GNU General Public License v3.0+](https://www.gnu.org/licenses/gpl-3.0)
