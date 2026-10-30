# Features

## Tooltips

KodiDevKit shows hover tooltips when the cursor rests on recognized content in Kodi skin XML files. The delay before showing is controlled by [`tooltip_delay`](settings.md#tooltips) (default: 200ms, set to -1 to disable).

### Tooltip types

**Labels**: Hovering over a numeric label ID (in `<label>`, `<label2>`, `<altlabel>`, `<property>`, `<hinttext>`) shows the translated text from `.po` files. Also works for `$LOCALIZE[id]` and `$ADDON[addon.id id]` expressions. In Python files, an id passed to `getLocalizedString`, directly or through the add-on's own wrapper functions, shows the text of the strings that call reads.

**Colors**: Hovering over a color name shows a swatch and alpha percentage for each definition, with the colors file it comes from. A hex value shows its own swatch.

**Includes and variables**: Hovering over `$VAR[Name]`, `$ESCVAR[Name]`, or `$EXP[Name]` shows a syntax-highlighted preview of the definition content. Inline `<include>IncludeName</include>` tags also show a preview when the cursor is on the name. An include's preview lists the params it takes above the source: each default, where it is passed on to another include, and any declared but unused. [`tooltip_include_params`](settings.md#tooltips) turns the list off.

**Maps**: Hovering the map name in `$MAP[Name, InfoLabel]` or `$ESCMAP[...]` previews the `<map>` definition. Hovering the infolabel instead fetches its live value and shows what the map turns it into.

**Control defaults**: Hovering the `type` value of a `<control>` previews the `<default type="...">` block that control inherits, when the skin defines one.

**Fonts**: Font name references show the font tag information.

**Constants**: Constant names show the defined value.

**Images**: Hovering over an image filename (`.png`, `.jpg`, `.gif`) shows dimensions and file size.

**Window names**: Hovering over an all-caps window name shows the window's XML filename.

**Conditions**: Hovering a condition in `<visible>`, `<enable>`, `<usealttexture>`, `<selected>`, `<expression>` or `<autoscroll>`, a `condition=""` attribute, or an include `<param>` used as a condition shows its verdict from the running Kodi: true, false, or not parseable. On the tag or attribute name the whole condition is evaluated; on one item, that item alone, with Kodi's help for it. Inside an include, each way its calls fill a `$PARAM` gets its own verdict. The verdict needs an active JSON-RPC connection; the help does not.

**InfoLabels**: Hovering inside `$INFO[...]` or `$ESCINFO[...]`, also in an include `<param>`, fetches the live value from Kodi via JSON-RPC.

## Auto-completion

Triggers automatically when typing in skin XML files. What it offers follows the tag or attribute the caret is in:

| Value | Completions |
|-------|-------------|
| Textures and paths | Files in the skin's `media/` folder |
| Colors | Color names the skin and Kodi define |
| Fonts | Font names from the current XML folder |
| Includes | Include names from the current XML folder |
| Control types, effects and other fixed values | The values Kodi accepts there |
| Conditions | Kodi's boolean conditions, with Kodi's help for each |
| Actions | Kodi's builtins, with Kodi's help for each |
| Inside a condition's parentheses | The values Kodi's help lists for that condition |

Completions are scoped to the current XML folder (e.g., `1080i/`). A completed condition or builtin gets a tab stop for each parameter.

## Keyboard shortcuts

| Shortcut | Context | Action |
|----------|---------|--------|
| `Shift+Enter` | Skin XML | Jump to include, variable, map, constant, font, label, or color definition |
| `Shift+Enter` | Kodi log | Jump to exception source file and line |
| `Ctrl+Enter` | Skin XML | Preview skin image |
| `Ctrl+Shift+Enter` | Skin XML | Switch XML folder (e.g., 1080i to 720p) |
| `Ctrl+Shift+X` | Skin XML | Replicate selected code with ascending numbers |
| `Ctrl+Shift+Y` | Skin XML | Evaluate math expression (x = selected integer) |
| `Ctrl+Shift+W` | Skin XML | Open Kodi Doxygen page for control type |
| `Ctrl+Shift+M` | Skin XML | Move selected text to language file |
| `Ctrl+Shift+O` | Any | Open Command Palette filtered to KodiDevKit commands |
| `=` | Skin XML tag, completions open | Insert `=""` after an attribute name |

## Fuzzy searches

Available via Command Palette (`Ctrl+Shift+P` > "KodiDevKit"):

- **Label search**: Search every string in the skin's and Kodi's `.po` files by text or id, and insert the pick's localize expression.
- **Image/texture search**: Search all media files with image preview, then insert the path or open the image.
- **Font search**: Search the fonts of the current XML folder and insert the name.
- **Translated strings of open file**: Search translated strings referenced in the currently open file.
- **Boolean condition search**: Search Kodi boolean conditions.
- **Builtin search**: Search Kodi builtin functions.
- **Dependency search**: List the Kodi repo's add-ons for this release with their versions; picking one opens its page on the Kodi mirror.
- **JSON-RPC search**: Search the running Kodi's JSON-RPC methods, types, and notifications.

## Context menu

Right-click in a skin XML file to access:

| Action | Description |
|--------|-------------|
| **Preview image** | Quick preview of the image path under the cursor |
| **Open image** | Open the image under the cursor in the system's default viewer |
| **Show info from Kodi Wiki** | Opens the Kodi Doxygen documentation page for the control type on the current line |
| **Move to language file** | Offers labels that match the selected text and a new one; the pick, added to `strings.po` when new, replaces the text with its localize expression |

## JSON-RPC

Real-time communication with a running Kodi instance. Requires [connection settings](settings.md#json-rpc) to be configured and Kodi's web server/JSON-RPC interface to be enabled (Settings > Services > Control).

### Commands

**Reload Skin**: Send a ReloadSkin() command to Kodi to refresh the active skin immediately.

**Execute builtin**: Run any Kodi builtin command from the Command Palette. Needs `script.toolbox` installed in Kodi. The previous command is remembered for quick re-execution.

**Display InfoLabels**: Enter comma-separated InfoLabel names (e.g., `Player.Title, Player.Duration`) to fetch their current values from Kodi.

**Display Booleans**: Enter comma-separated boolean conditions (e.g., `Player.HasVideo, System.HasAddon(script.toolbox)`) to evaluate them against the running Kodi instance.

**Open active Window XML**: Opens the XML file for the window currently displayed in Kodi.

**Browse Kodi VFS**: Navigate Kodi's virtual filesystem (video/music libraries) via quick panel.

### Output modes

Results display is controlled by [`json_rpc_output_mode`](settings.md#json-rpc-display):

| Mode | Behavior |
|------|----------|
| `output_panel` (default) | Results appear in the bottom output panel with minimal formatting |
| `scratch_view` | Results open in a dedicated tab with headers and borders, useful for comparing multiple queries |

## Kodi log

**Open log**: Command Palette: "KodiDevKit: Open Log". Opens `kodi.log` from the standard userdata location.

**Jump to exception source**: In a Kodi log file, place the cursor on a Python traceback line and press `Shift+Enter` to jump to the referenced source file and line number.

**Userdata log**: "KodiDevKit: Open Userdata Log", shown on Windows when `portable_mode` is set, opens `kodi.log` from `%APPDATA%/Kodi/`.

## Miscellaneous

**Set Kodi folder**: Command Palette: "KodiDevKit: Set Kodi Folder". Sets the `kodi_path` setting.

**Auto-reload skin**: When [`auto_reload_skin`](settings.md#auto-reload) is enabled, saving a window XML or color file automatically sends a reload command to Kodi via JSON-RPC.

**TexturePacker**: Command Palette: "KodiDevKit: Build Skin" / "KodiDevKit: Build Theme". Requires [`texturepacker_path`](settings.md#build-and-packaging) to be set. Build Skin packs the skin's images into `media/Textures.xbt` and asks where to save an installable zip, starting in the skin's folder as `<id>-<version>.zip`. Build Theme packs the picked theme into `media/<theme>.xbt`.

**Color picker**: If the [ColorPicker](https://packagecontrol.io/packages/ColorPicker) plugin is installed, "KodiDevKit: Choose color" launches it and inserts a Kodi-formatted color string (`FFrrggbb`).

**Math expressions**: `Ctrl+Shift+Y` opens an input panel to evaluate a math expression where `x` is the selected integer and `i` is the selection index.

**Element row replication**: `Ctrl+Shift+X` duplicates the selected XML block with ascending numbers. The `[N]` pattern in the selection is replaced with incrementing values.

**Switch to addon**: Command Palette: "KodiDevKit: Switch to Add-on". Shows a list of installed addons from Kodi's userdata folder and opens the selected one in a new Sublime Text window.

**Bump addon version**: Command Palette: "KodiDevKit: Bump addon version". Offers the next major, minor and bugfix versions or one you type, sets it in `addon.xml`, and adds a blank news entry, plus one in `changelog.txt`, to fill in.

**Reload language files**: Command Palette: "KodiDevKit: Reload Language Files". Re-reads `.po` translation files without restarting Sublime Text.

**Open validation report**: Command Palette: "KodiDevKit: Open Validation Report". Opens the skin's HTML validation report in the browser without running the checks again, or a picker of the reports when [`validation_report_directory`](settings.md#validation) is set.

**Syntax highlighting**: Custom syntax definitions for Kodi language files (`.po`), Kodi SkinXML, and Kodi log files.

## Remote actions (ADB)

For Android-based Kodi devices (Shield, Fire TV, etc.). Runs `adb` from the PATH, or from [`adb_path`](settings.md#adb-and-remote) when set. All actions are accessed via Command Palette: "KodiDevKit: Remote Actions", which opens a quick panel with:

- Set remote IP
- Connect to remote device
- Push addon to remote
- Pull log from remote
- Clear temp folder on remote
- Pull screenshot from remote
- Reboot remote device
