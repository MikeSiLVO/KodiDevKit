# Settings

All settings are configured in `kodidevkit.sublime-settings`. Open via Preferences > Package Settings > KodiDevKit, or edit the file directly.

User overrides go in `Packages/User/kodidevkit.sublime-settings`.

## Kodi connection

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `kodi_path` | string | `""` | Full path to your Kodi installation folder. Used to locate core language files, addons, and userdata. Empty, or a folder without Kodi's `colors.xml` and `strings.po`, uses the copies bundled for the targeted release. Backslashes must be escaped on Windows (`C:\\Program Files\\Kodi`). |
| `portable_mode` | bool | `false` | Set to `true` if Kodi runs in portable mode (userdata inside the Kodi installation folder). |
| `userdata_folder` | string | `""` | Explicit override for Kodi's userdata folder path. Leave empty to auto-detect based on `kodi_path` and `portable_mode`. |

## JSON-RPC

Configure the connection to Kodi's JSON-RPC interface. Enable it in Kodi under Settings > Services > Control > Allow remote control via HTTP.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `kodi_address` | string | `"http://192.168.1.100:8080"` | Full base URL to your Kodi instance. If set, overrides the component settings below. |
| `kodi_scheme` | string | `"http"` | Protocol (`http` or `https`). Used when `kodi_address` is not set. |
| `kodi_host` | string | `"localhost"` | Hostname or IP address. Used when `kodi_address` is not set. |
| `kodi_port` | int | `8080` | JSON-RPC port. Used when `kodi_address` is not set. |
| `kodi_username` | string | `"kodi"` | Username for basic authentication. |
| `kodi_password` | string | `""` | Password for basic authentication. |
| `token` | string | `""` | Bearer token. If set, used instead of username/password. |

**Typical setup:** Set `kodi_address` to `"http://localhost:8080"` if Kodi runs on the same machine, or `"http://192.168.1.X:8080"` for a remote instance.

## Language

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `language` | string | `"en_gb"` | Language code for Kodi's core strings. Format: ISO 639-1 with optional region (e.g., `en_gb`, `de_de`, `fr_fr`). The plugin prepends `resource.language.` if not present. |
| `language_folders` | list | `["resource.language.en_gb", "English"]` | Ordered list of language folders to search for `.po` files. First match is used. |

## Validation

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `auto_skin_check` | bool | `true` | Run validation checks automatically when saving XML files. Results appear as inline phantoms. |
| `phantom_severity_level` | string | `"warning"` | Minimum severity for on-save phantoms. Values: `"error"`, `"warning"`. Full reports always show everything. |
| `hide_include_warnings` | bool | `true` | Hide warnings that originate from include content, everywhere: on-save phantoms, the validation results view, and the HTML report's initial state. Errors from includes are always shown, and `Defaults.xml` issues are reported at their source (not treated as include warnings). Set `false` to show them. |
| `kodi_release` | string | `""` | Release to validate against: `"omega"` (Kodi 21) or `"piers"` (Kodi 22). Empty uses the release the skin's `xbmc.gui` import names, or the newest when it names none. An unknown value is reported and ignored. |
| `validation_exclude` | list | `["shortcuts"]` | Folder or file names XML Validation skips, on save and in the report. Matches any path component, so `"shortcuts"` skips any file inside a `shortcuts/` folder. |
| `validation_report_directory` | string | `""` | Folder for the HTML validation report. Empty writes `validation_report.html` into the skin's folder, replaced on each run. A folder given here holds one `<skin>_validation_report.html` per skin. |

**`phantom_severity_level` values:**
- `"error"`: only errors (broken brackets, invalid values, conditions Kodi cannot parse).
- `"warning"`: errors and warnings (invalid tags, repeated tags). The default.

See [Validation](validation.md) for details on what each validator checks.

## Tooltips

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `tooltip_delay` | int | `200` | Milliseconds before showing hover tooltips. Set to `-1` to disable tooltips entirely. |
| `tooltip_width` | int | `1000` | Maximum tooltip width in pixels. |
| `tooltip_height` | int | `400` | Maximum tooltip height in pixels. |

## Auto-reload

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `auto_reload_skin` | bool | `false` | Automatically reload the Kodi skin after saving window XML or color files. Requires an active JSON-RPC connection. |

## JSON-RPC display

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `json_rpc_output_mode` | string | `"output_panel"` | How JSON-RPC results are displayed. `"output_panel"` shows results in the bottom panel. `"scratch_view"` opens a dedicated tab with formatted headers. |

## Build and packaging

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `texturepacker_path` | string | `""` | Full path to Kodi's TexturePacker utility. Required for "Build Skin" and "Build Theme" commands. |

## ADB and remote

For deploying to Android-based Kodi devices.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `adb_path` | string | `""` | Full path to the `adb` executable. Empty runs `adb` from the PATH. |
| `remote_ip` | string | `""` | Device address `adb` connects to, as `ip` or `ip:port`. Remote Actions can also set it. |
| `remote_userdata_folder` | string | `""` | Kodi userdata path on the remote device. |

## Debugging

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `debug_mode` | bool | `false` | Enable verbose logging to Sublime's console (View > Show Console, `Ctrl+\``). |
| `enable_file_logging` | bool | `false` | Log to a rotating file for diagnosing freezes. 5MB per file, 5 backups (30MB total). Log location is shown in the console on startup. |

**Log file locations when `enable_file_logging` is enabled:**

| OS | Path |
|----|------|
| Windows | `%LOCALAPPDATA%\Sublime Text\Cache\KodiDevKit\logs\kodidevkit_debug.log` |
| Linux | `~/.cache/sublime-text/Cache/KodiDevKit/logs/kodidevkit_debug.log` |
| macOS | `~/Library/Caches/Sublime Text/Cache/KodiDevKit/logs/kodidevkit_debug.log` |
