# Validation

KodiDevKit validates your skin at two levels: per-file checks on save (XML structure) and full-skin reports covering variables, includes, maps, labels, fonts, IDs, images, and more.

## Severity levels

| Level | Meaning | Examples |
|-------|---------|----------|
| **Error** | Must fix. Blocks Kodi repo submission or causes visible breakage. | Missing image, undefined include, BOM in file, empty action without `noop` |
| **Warning** | Kodi handles it, but the code is wrong or sloppy. | Case mismatch in font name, invalid tag (silently ignored by Kodi) |

Unused variables and includes are errors, not warnings -- the Kodi repo review process blocks PRs with dead definitions.

## On-save phantoms vs full reports

KodiDevKit validates in two modes with different defaults:

**On-save phantoms** appear inline after saving an XML file, controlled by [`auto_skin_check`](settings.md#validation) (default: `true`). These run the XML interpreter against the saved file only (tags, attributes, values, brackets) -- not the full-skin checks like unused variables or missing images. They are filtered:
- `phantom_severity_level` controls the minimum severity shown (default: `warning`, showing both errors and warnings).
- `hide_include_warnings` (default: `true`) suppresses warnings that originate from include content, since an include may be valid in other contexts. Errors from includes are always shown. This is a plugin-wide setting -- it also applies to the results view and the HTML report.
- Phantoms show navigation links (Next Issue, Dismiss) and group multiple issues per line.

**Full reports** (Command Palette: "KodiDevKit: Generate Validation Report") run 9 checks across the entire skin: Variables, Includes, Maps, Labels, Fonts, IDs, Images, XML Validation, and File Integrity. They open in the browser as an interactive HTML page with:
- Toggle buttons for errors, warnings, and include-originated warnings. Errors and warnings show by default; include warnings start hidden, following `hide_include_warnings`.
- Category sections (Variables, Includes, Labels, etc.) with issue counts and descriptions.
- Clickable file paths that open the file in Sublime Text at the correct line.
- Export to text that mirrors the active toggles.

**Individual checks** can also be run from the Command Palette:

| Command | Check |
|---------|-------|
| KodiDevKit: Check Variables | Variables |
| KodiDevKit: Check Includes | Includes |
| KodiDevKit: Check Maps | Maps |
| KodiDevKit: Check Labels | Labels |
| KodiDevKit: Check Fonts | Fonts |
| KodiDevKit: Check Images | Images |
| KodiDevKit: Check Control / Window IDs | IDs |
| KodiDevKit: Check for invalid Nodes / Attributes | XML structure |

File Integrity and Expressions do not have individual commands -- they run as part of the full report and on-save validation respectively.

Results open in a read-only results view grouped by file -- double-click a line (or F4 / Shift+F4) to jump to the issue. Useful when you want to run one check without generating a full report.

## Kodi release

Validation targets the release the skin declares in `addon.xml` via `<import addon="xbmc.gui">` -- gui 5.17.0 is Omega, 5.18.0 is Piers. The `kodi_release` setting overrides the detected value.

The release picks the control schema, the window table, the builtin and boolean-condition completions, and the bundled `colors.xml` / `strings.po`, so anything Kodi added in a later release is an error on an older skin.

`scripts/update_kodi_refs.py` refreshes `colors.xml` / `strings.po` from upstream. The builtin and condition lists in `data/<release>/data.xml` are maintained by hand: take new names from the registration maps in `GUIInfoManager.cpp` and `xbmc/interfaces/builtins/`, since doxygen both misses names and keeps ones Kodi has deleted.

Piers-only skinning so far:

| Feature | Surface |
|---------|---------|
| Skin maps | `<map>` / `<entry>`, `$MAP[]`, `$ESCMAP[]` |
| FixedList movement and alignment | `<startmovement>`, `<endmovement>`, `<aligny>` on `fixedlist` |
| Image scaling filters | `<imagefilter>`, `<diffusefilter>` on `image` (`linear` or `nearest`) |
| EPG grid block size | `<minspertimeblock>` on `epggrid` |
| Player bookmarks | `Player.Bookmarks` infolabel, `Player.HasBookmarks` boolean |
| Stream-select dialogs | `dialogselectvideo` (12300), `dialogselectaudio` (12301), `dialogselectsubtitle` (12302); `selectvideoversion` and `selectvideoextra` are gone |
| PVR providers, game disc manager | `tvproviders` (10712), `radioproviders` (10713), `gamediscmanager` (10832) |
| New boolean conditions | `Player.IsLive`, `RetroPlayer.AchievementsLoggedIn`, `RetroPlayer.DiscEjected`, `RetroPlayer.EmptyTray`, `RetroPlayer.SupportsEject` |

## Validators

### Variables

Checks `$VAR[Name]` and `$ESCVAR[Name]` references against variable definitions.

**Errors:**
- Variable referenced but not defined in any `<variable name="...">` block.
- Variable defined but never referenced anywhere in the skin.

**`$PARAM` resolution:** Variable names containing `$PARAM[...]` are resolved with nested bracket matching. For example, `$VAR[Label_Title_C$PARAM[id]3]` correctly extracts the full name including the nested parameter.

**SkinShortcuts awareness:** Scans `shortcuts/template.xml` (v2) or `shortcuts/templates.xml` (v3) for `$VAR[Name]` references to avoid false "unused" reports. References containing `$SKINSHORTCUTS[...]` or `$PROPERTY[...]` are skipped as runtime placeholders.

See also: [SkinShortcuts integration](skinshortcuts.md)

### Includes

Checks `<include>Name</include>` and `<include content="Name">` references against include definitions.

**Errors:**
- Include referenced but not defined.
- Include defined but never referenced.

**Runtime pattern suppression:** When `script.skinshortcuts` or `script.skinvariables` is detected as a dependency in `addon.xml`, references matching these patterns are suppressed (not flagged as undefined):
- `skinshortcuts-*` -- script.skinshortcuts generated includes
- `skinvariables-*` -- script.skinvariables generated includes
- `[digits]menu` (e.g., `0menu`, `3menu`) -- SkinShortcuts menu IDs
- `script-*-includes` -- dynamic script includes

**SkinShortcuts template scanning:** Static `<include>` tags and `content`/`include` attributes in template files are checked against known include names to mark them as used.

### Maps

Checks `$MAP[Name, InfoLabel]` and `$ESCMAP[...]` references against `<map name="...">` definitions. Skin maps arrived in Kodi 22 (Piers); a skin targeting an older release is told so once.

**Errors:**
- Map referenced but not defined.
- Map defined but nothing reaches it, directly or through another map's `ref`.
- `$MAP[]` with fewer than two arguments, or a blank map name or infolabel. Kodi needs both and renders nothing without them.
- `$MAP[` with no closing `]`. Kodi discards the rest of the label.
- A definition Kodi silently drops: `<map>` with no `name`, `<entry>` with no `key` or no text, a map with neither entries nor a `ref`.
- Duplicate map name (the last definition wins) or duplicate `<entry key>` within one map (the first value wins).
- `ref` naming a map that is not defined, or a `ref` chain that loops back on itself.
- A `name` or `ref` padded with whitespace. `$MAP[]` trims the name it looks up, so a padded definition can never be reached.

**Warnings:** a child of `<map>` other than `<entry>` (reported by the XML structure check).

Hovering the map name in a `$MAP[]` shows the definition; hovering the infolabel queries the running Kodi and shows the value and what the map turns it into.

### Labels

Checks label references and text content in label-like tags (`<label>`, `<label2>`, `<altlabel>`, `<property>`, `<hinttext>`).

**Errors:**
- Numeric label ID (`$LOCALIZE[12345]` or bare `12345` in a label tag) not found in any `.po` translation file.

**Warnings:**
- Hardcoded text that should be in a language file (untranslated strings).
- Bare InfoLabel expressions (e.g., `Player.Title`) that may need a `$INFO[]` wrapper.
- Possible addon ID used as a label.

**Filtering:** Brand names (Kodi, YouTube, Netflix, etc.) and technical terms (HDR, PVR, HEVC, etc.) are not flagged as untranslated strings since they remain the same across languages.

**Generated file exclusion:** `script-skinshortcuts-includes.xml` is excluded from label/ID validation since its content is generated at runtime.

### Fonts

Validates font definitions in `Font.xml` / `Fonts.xml` and font references throughout the skin.

**Errors:**
- Missing font file -- `<filename>` references a `.ttf`/`.otf` that doesn't exist in `fonts/` or Kodi's core font directories.
- Font referenced in XML but not defined in any `<fontset>`.
- Missing required elements in a `<font>` definition.
- No unicode fontset defined.
- Missing `font13` -- required by Kodi internally.

**Warnings:**
- Case mismatch in font name references (Kodi resolves fonts case-insensitively, but sloppy references indicate maintenance issues).
- Unused font definitions.
- Cross-fontset inconsistencies -- font exists in one fontset but not another.
- Duplicate font names within a fontset.
- Non-TTF/OTF font files or filenames without extensions.

Font filename issues point at the `<filename>` line in Fonts.xml, not the `<font>` parent.

### IDs

Validates control and window ID references.

**Errors:**
- Window ID referenced but not defined by any window XML file.
- Control ID referenced (via `<onup>`, `<onfocus>`, etc.) but not defined in the same window's control tree.
- Numeric window ID used where Kodi expects a window name.

**Scope:** IDs are validated per-window. Each window's resolved tree (includes expanded, parameters substituted) provides the full set of defined control IDs. Plugin/widget IDs (9xxxx range) are excluded from validation.

### Images

Validates image file references against files on disk.

**Errors:**
- Image file not found on disk -- will render as blank in Kodi.

**Warnings:**
- Case mismatch in image path (works on Windows and in Textures.xbt, but breaks on case-sensitive filesystems like Linux).
- Wrong relative path.

**Textures.xbt:** If a `Textures.xbt` file is detected in the skin's `media/` folder, image validation is skipped entirely since packed textures cannot be verified.

**Reporting:** Issues are reported per usage location. If the same missing image is referenced in 5 places, 5 issues are generated with file/line information for each usage.

### XML Structure

The interpreter walks the resolved XML tree (after include expansion, constant/expression resolution, and default application) and validates structural correctness at each level.

**Errors:**
- Invalid color values (not a valid ARGB hex or recognized color name).
- Invalid integer values in tags that require integers.
- Empty action tags that should use `noop` (e.g., `<onclick></onclick>` instead of `<onclick>noop</onclick>`).

**Warnings:**
- Invalid tag -- a tag appears in a context where Kodi doesn't expect it (e.g., `<label>` directly inside `<window>`).
- Invalid attribute -- an attribute not recognized for the given tag.
- Invalid attribute value -- value outside the allowed enumeration (e.g., `align="middle"` instead of `align="center"`).
- Duplicate singleton tags -- tags like `<visible>` or `<enable>` that should appear at most once per control.
- Bracket mismatch in condition expressions (`<visible>`, `<enable>`, `<onclick>`, etc.).

Kodi silently ignores all of these structural issues. They are flagged to teach correct XML structure and catch typos.

`<default type="X">` blocks (e.g. in `Defaults.xml`) are validated at their own source against control type X's schema, so a malformed default is reported once at `Defaults.xml` rather than on every control that inherits it -- and is never treated as an include warning.

### Expressions (on-save only)

Validates that dynamic expressions (`$VAR[]`, `$INFO[]`, `$MAP[]`, `$LOCALIZE[]`) are only used in tags that support them. This check runs during on-save validation but is not included in full reports.

**Errors:**
- Expression used in a literal-only tag. For example, `<posx>$VAR[XPos]</posx>` is invalid because `<posx>` is parsed with `XMLUtils::GetFloat` which doesn't resolve expressions.

Tags that support expressions include labels, conditions, colors, and the primary `<texture>` tag. Tags that require literals include positioning (`posx`, `width`), timing (`scrolltime`), IDs, font names, and all static texture variants (`texturefocus`, `texturenofocus`, etc.).

`$PARAM[]` is an exception -- it works universally in all tags because it's resolved during include processing, before Kodi's control factory sees the XML.

### File Integrity

Checks file encoding and line endings across the entire skin directory.

**Errors:**
- BOM (Byte Order Mark) detected in any XML file.
- Windows line endings (`\r\n`) detected in any file.
- Mac line endings (`\r`) detected in any file.

All of these block Kodi repo submission.

## Settings that affect validation

| Setting | Default | Effect |
|---------|---------|--------|
| [`auto_skin_check`](settings.md#validation) | `true` | Run validation on save |
| [`phantom_severity_level`](settings.md#validation) | `"warning"` | Minimum severity for on-save phantoms |
| [`hide_include_warnings`](settings.md#validation) | `true` | Hide include-originated warnings (phantoms, results view, report) |
| [`validation_exclude`](settings.md#validation) | `["shortcuts"]` | Paths to skip during validation |
| [`validation_report_directory`](settings.md#validation) | `""` (auto) | Where HTML reports are saved |

See [Settings](settings.md) for full details.
