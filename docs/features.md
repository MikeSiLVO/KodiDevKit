# Features

## Tooltips

KodiDevKit shows hover tooltips when the cursor rests on recognized content in Kodi skin XML files. The delay before showing is controlled by [`tooltip_delay`](settings.md#tooltips) (default: 200ms, set to -1 to disable).

### Tooltip types

**Labels** -- Hovering over a numeric label ID (in `<label>`, `<label2>`, `<altlabel>`, `<property>`, `<hinttext>`) shows the translated text from `.po` files. Also works for `$LOCALIZE[id]` and `$ADDON[addon.id id]` expressions, and for numeric IDs in Python source files on lines containing "label", "lang", or "string".

**Colors** -- Hovering over a color name shows hex value, alpha percentage, and theme variants.

**Includes and variables** -- Hovering over `$VAR[Name]`, `$ESCVAR[Name]`, or `$EXP[Name]` shows a syntax-highlighted preview of the definition content. Inline `<include>IncludeName</include>` tags also show a preview when the cursor is on the name.

**Fonts** -- Font name references show the font tag information.

**Constants** -- Constant names show the defined value.

**Images** -- Hovering over an image filename (`.png`, `.jpg`, `.gif`) shows dimensions and file size.

**Window names** -- Hovering over an all-caps window name shows the window's XML filename.

**Conditions** -- Hovering inside `<visible>`, `<enable>`, `<usealttexture>`, `<selected>`, or `<expression>` tags evaluates the boolean condition against the running Kodi instance via JSON-RPC and shows True/False. Also evaluates `condition=""` attributes. Requires an active JSON-RPC connection.

**InfoLabels** -- Hovering inside `$INFO[...]` or `$ESCINFO[...]` fetches the live value from Kodi via JSON-RPC.

## Auto-completion

Triggers automatically when typing in skin XML files. Provides completions for:

| Type | Source |
|------|--------|
| Media files | Skin's `media/` folder (cached for 30s) |
| Colors | Theme color definitions with hex preview |
| Includes | Include names from the current resolution folder |
| Fonts | Font names from the current resolution folder |
| Variables | Not in completions (use `$VAR[...]` syntax) |
| Constants | Not in completions (use `$CONSTANT[...]` syntax) |
| Builtins | Kodi builtin functions with parameter placeholders |
| Boolean conditions | Kodi condition expressions |
| Window names | Kodi window identifiers |

Completions are scoped to the current XML folder (e.g., `1080i/`). Builtin function parameters are converted to tab-stop placeholders.

## Keyboard shortcuts

| Shortcut | Context | Action |
|----------|---------|--------|
| `Shift+Enter` | Skin XML | Jump to include, variable, constant, font, label, or color definition |
| `Shift+Enter` | Kodi log | Jump to exception source file and line |
| `Ctrl+Enter` | Skin XML | Preview skin image |
| `Ctrl+Shift+Enter` | Skin XML | Switch XML folder (e.g., 1080i to 720p) |
| `Ctrl+Shift+X` | Skin XML | Replicate selected code with ascending numbers |
| `Ctrl+Shift+Y` | Any | Evaluate math expression (x = selected integer) |
| `Ctrl+Shift+W` | Skin XML | Open Kodi Doxygen page for control type |
| `Ctrl+Shift+M` | Any | Move selected text to language file |
| `Ctrl+Shift+O` | Any | Open Command Palette filtered to KodiDevKit commands |
| `Enter` | Completion view | Accept and close KodiDevKit completion view |

## Fuzzy searches

Available via Command Palette (`Ctrl+Shift+P` > "KodiDevKit"):

- **Label search** -- Search all skin labels by ID or text.
- **Image/texture search** -- Search all media files with image preview.
- **Font search** -- Search all font definitions.
- **Translated string search** -- Search `.po` translation entries.
- **Translated strings of open file** -- Search translated strings referenced in the currently open file.
- **Boolean condition search** -- Search Kodi boolean conditions.
- **Builtin search** -- Search Kodi builtin functions.
- **Dependency search** -- Search addon dependencies.
- **JSON-RPC search** -- Search JSON-RPC methods, types, and notifications.

## Context menu

Right-click in a skin XML file to access:

| Action | Description |
|--------|-------------|
| **Preview image** | Quick preview of the image path under the cursor |
| **Open image** | Open the image file directly in Sublime Text |
| **Show info from Kodi Wiki** | Opens the Kodi Doxygen documentation page for the control type on the current line |
| **Move to language file** | Extracts the selected hardcoded text, adds it to `strings.po` with the next available ID, and replaces the text with `$LOCALIZE[id]` |

## JSON-RPC

Real-time communication with a running Kodi instance. Requires [connection settings](settings.md#json-rpc) to be configured and Kodi's web server/JSON-RPC interface to be enabled (Settings > Services > Control).

### Commands

**Reload Skin** -- Send a ReloadSkin() command to Kodi to refresh the active skin immediately.

**Execute builtin** -- Run any Kodi builtin command from the Command Palette. Uses `script.toolbox` addon to execute. The previous command is remembered for quick re-execution.

**Display InfoLabels** -- Enter comma-separated InfoLabel names (e.g., `Player.Title, Player.Duration`) to fetch their current values from Kodi.

**Display Booleans** -- Enter comma-separated boolean conditions (e.g., `Player.HasVideo, System.HasAddon(script.toolbox)`) to evaluate them against the running Kodi instance.

**Open active Window XML** -- Opens the XML file for the window currently displayed in Kodi.

**Browse Kodi VFS** -- Navigate Kodi's virtual filesystem (video/music libraries) via quick panel.

### Output modes

Results display is controlled by [`json_rpc_output_mode`](settings.md#json-rpc-display):

| Mode | Behavior |
|------|----------|
| `output_panel` (default) | Results appear in the bottom output panel with minimal formatting |
| `scratch_view` | Results open in a dedicated tab with headers and borders, useful for comparing multiple queries |

## Kodi log

**Open log** -- Command Palette: "KodiDevKit: Open Log". Opens `kodi.log` from the standard userdata location.

**Jump to exception source** -- In a Kodi log file, place the cursor on a Python traceback line and press `Shift+Enter` to jump directly to the referenced source file and line number.

**Userdata log** -- "KodiDevKit: Open Userdata Log" opens the log from the `%APPDATA%/Kodi/` location (useful on Windows in portable mode).

## Miscellaneous

**Set Kodi folder** -- Command Palette: "KodiDevKit: Set Kodi Folder". Quick way to set the `kodi_path` setting without editing the settings file.

**Auto-reload skin** -- When [`auto_reload_skin`](settings.md#auto-reload) is enabled, saving a window XML or color file automatically sends a reload command to Kodi via JSON-RPC.

**TexturePacker** -- Command Palette: "KodiDevKit: Build Skin" / "KodiDevKit: Build Theme". Requires [`texturepacker_path`](settings.md#build-and-packaging) to be set.

**Color picker** -- If the [ColorPicker](https://packagecontrol.io/packages/ColorPicker) plugin is installed, "KodiDevKit: Choose color" launches it and inserts a Kodi-formatted color string (`FFrrggbb`).

**Math expressions** -- `Ctrl+Shift+Y` opens an input panel to evaluate a math expression where `x` is the selected integer and `i` is the selection index. Useful for calculating positions.

**Element row replication** -- `Ctrl+Shift+X` duplicates the selected XML block with ascending numbers. The `[N]` pattern in the selection is replaced with incrementing values.

**Switch to addon** -- Command Palette: "KodiDevKit: Switch to Add-on". Shows a list of installed addons from Kodi's userdata folder and opens the selected one in a new Sublime Text window.

**Bump addon version** -- Command Palette: "KodiDevKit: Bump addon version". Increments the version number in `addon.xml`.

**Reload language files** -- Command Palette: "KodiDevKit: Reload Language Files". Re-reads `.po` translation files without restarting Sublime Text.

**Open validation report** -- Command Palette: "KodiDevKit: Open Validation Report". Opens the most recent HTML validation report in the browser.

**Syntax highlighting** -- Custom syntax definitions for Kodi language files (`.po`), Kodi SkinXML, and Kodi log files.

## Remote actions (ADB)

For Android-based Kodi devices (Shield, Fire TV, etc.). Requires [`adb_path`](settings.md#adb-and-remote) to be configured. All actions are accessed via Command Palette: "KodiDevKit: Remote Actions", which opens a quick panel with:

- Set remote IP
- Connect to remote device
- Push addon to remote
- Pull log from remote
- Clear temp folder on remote
- Pull screenshot from remote
- Reboot remote device
