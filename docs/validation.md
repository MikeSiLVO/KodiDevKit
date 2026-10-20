# Validation

KodiDevKit validates your skin at two levels: the XML check on save, and a full report covering variables, includes, maps, labels, fonts, IDs, images, XML structure, file integrity and the Kodi repo rules.

## Severity levels

| Level | Meaning | Examples |
|-------|---------|----------|
| **Error** | Must fix. Blocks Kodi repo submission or causes visible breakage. | Missing image, undefined include, BOM in file, empty action without `noop` |
| **Warning** | Kodi handles it, but the code is wrong or sloppy. | Invalid tag (silently ignored by Kodi), a tag that repeats its `<default>` |

Unused variables and includes are errors, not warnings: the Kodi repo review process blocks PRs with dead definitions.

## On-save phantoms vs full reports

KodiDevKit validates in two modes with different defaults:

**On-save phantoms** appear inline after saving an XML file, controlled by [`auto_skin_check`](settings.md#validation) (default: `true`). They run the XML structure check against the saved file only, not the full-skin checks like unused variables or missing images. They are filtered:
- `phantom_severity_level` controls the minimum severity shown (default: `warning`, showing both errors and warnings).
- `hide_include_warnings` (default: `true`) suppresses warnings that originate from include content, since an include may be valid in other contexts. Errors from includes are always shown. This is a plugin-wide setting; it also applies to the results view and the HTML report.
- Phantoms show navigation links (Next Issue, Dismiss) and group multiple issues per line.

**Full reports** (Command Palette: "KodiDevKit: Generate Validation Report") run all 10 checks across the entire skin: Variables, Includes, Maps, Labels, Fonts, IDs, Images, XML Validation, File Integrity and Kodi Repo. The report is saved in the skin's folder, or in [`validation_report_directory`](settings.md#validation) when set, and opens in the browser as an interactive HTML page with:
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
| KodiDevKit: Check File Integrity | File Integrity |
| KodiDevKit: Check Kodi Repo Rules | Kodi Repo |

Results open in a read-only results view grouped by file; double-click a line (or F4 / Shift+F4) to jump to the issue. Useful when you want to run one check without generating a full report.

## Kodi release

Validation targets the release the skin declares in `addon.xml` via `<import addon="xbmc.gui">`: gui 5.17.0 is Omega, 5.18.0 is Piers. The `kodi_release` setting overrides the detected value.

The release picks the control schema, the window table, the builtin and boolean-condition completions, and the bundled `colors.xml` / `strings.po`, so anything Kodi added in a later release is an error on an older skin.

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
- Variable defined but never referenced. A variable named in a `SetProperty()` value counts as referenced.
- Variable defined twice. Kodi uses the first definition.

**`$PARAM` resolution:** Variable names containing `$PARAM[...]` are resolved with nested bracket matching, so `$VAR[Label_Title_C$PARAM[id]3]` is read as one name.

**SkinShortcuts awareness:** `$VAR[Name]` references in `shortcuts/templates.xml` (v3) or `shortcuts/template.xml` (v2) count as referenced. References containing `$SKINSHORTCUTS[...]` or `$PROPERTY[...]` are skipped as runtime placeholders.

See also: [SkinShortcuts integration](skinshortcuts.md)

### Includes

Checks `<include>Name</include>` and `<include content="Name">` references against include definitions, and the files `<include file="...">` loads.

**Errors:**
- Include referenced but not defined.
- Include defined but never referenced.
- Include defined twice. Kodi uses the first definition.
- Include with `<param>` children but no `<definition>`. Kodi ignores it.
- `<include file="...">` naming a file that is missing, differs only by case, or lies outside the skin folder.
- An `Includes.xml` named with different case. Kodi looks for `Includes.xml` exactly.

**Runtime names:** References to `skinshortcuts-*`, `skinvariables-*` and `script-*-includes` are never reported as undefined, and neither is a missing `<include file="script-*-includes.xml">`. Add-ons write these at runtime.

**SkinShortcuts template scanning:** Static `<include>` tags and `content`/`include` attributes in template files count as references.

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
- A skin string outside 31000-31999. Kodi 22 reads those ids as its own strings.
- A string in a `strings.po` that does not close, or has text or spaces after its closing quote. Kodi shows it empty, cut short, or in English instead of the translation.

**Warnings:**
- Hardcoded text that should be in a language file.
- An infolabel such as `Player.Art(fanart)` written without `$INFO[]`, which Kodi shows as plain text.
- An add-on id such as `plugin.video.foo` written as a label.

**Filtering:** Brand names (Kodi, YouTube, Netflix, etc.) and technical terms (HDR, PVR, HEVC, etc.) are not flagged as untranslated since they read the same in every language.

**Generated file exclusion:** `script-skinshortcuts-includes.xml` is left out of the label, ID, font and image checks since its content is generated at runtime.

### Fonts

Validates font definitions in `Font.xml` and font references throughout the skin.

**Errors:**
- Font referenced but not defined in `Font.xml`, or defined only with different case.
- Font whose file does not end in `.ttf`, including a file with no extension. Kodi never loads it.
- Missing font file: `<filename>` names a file found neither in `fonts/` nor in Kodi's core fonts.
- A `<font>` without `<name>` or `<filename>`, or with a negative or non-numeric size.
- No `font13`, which Kodi needs.
- `-` or `noop` used as a font name. Kodi has no empty font.

**Warnings:**
- Case mismatch in a font filename. Kodi still loads it.
- Unused font definition.
- A fontset missing fonts that the first fontset defines, or missing `font13`.
- Duplicate font name within a fontset.
- The obsolete `unicode` attribute on a fontset. Kodi ignores it.

Font filename issues point at the `<filename>` line in `Font.xml`, not the `<font>` parent.

### IDs

Validates control and window ID references.

**Errors:**
- Window ID referenced but not defined by any window XML file.
- Window name Kodi does not recognize.
- Control ID referenced (via `<onup>`, `<onfocus>`, conditions, actions) but not defined in that window.
- A custom window Kodi refuses to load: no id, a root other than `<window>`, or an id Kodi uses for its own window. Two custom windows sharing an id, of which Kodi loads one.

**Warnings:**
- A custom window id outside 1100-1199.
- Kodi's own window referred to by number where it has a name; the number still works.

**Scope:** A control ID must exist in the window that refers to it, counting its includes and Kodi's own controls for that window. References inside include files are not checked, since they have no window of their own. In modeless dialogs and add-on windows, after a window switch, and in a dialog's `<onunload>`, an ID defined anywhere in the skin is accepted, except in navigation tags such as `<onup>`.

### Images

Validates image file references against files on disk.

**Errors:**
- Image file not found, so Kodi shows nothing. Windows an add-on opens are left alone, since Kodi also searches the add-on's own media.
- A placeholder such as `-` as an image value. Kodi has no empty texture; leave the value empty.
- A texture bundle Kodi cannot read.
- A `special://skin/media/` image path. The Kodi repo packs `media/` into `Textures.xbt`, so a repo install has no file there; write the path without `special://skin/media/`.
- Case mismatch in a `special://skin/` image path. Kodi never reads that path from `Textures.xbt`, so it breaks on case-sensitive filesystems like Linux.

**Warnings:**
- Case mismatch in a bare image path (works on Windows and in `Textures.xbt`, but breaks on case-sensitive filesystems like Linux).
- An image not at its path but elsewhere in the skin, with where Kodi looks and where the file is.
- `Textures.xbt` shipped beside the loose source images in `media/`.
- An image found only in `Textures.xbt`, not among the loose images. The Kodi repo packs `Textures.xbt` from the loose images, so a repo build drops it.

**Paths:** A bare path is looked up in `media/`. A `special://skin/` path starts at the skin folder and is read from disk only, never from `Textures.xbt`.

**Textures.xbt:** When `media/` holds only a `Textures.xbt`, `media/` references are checked against the images packed in it, without regard to case.

**Reporting:** Issues are reported per usage location. If the same missing image is referenced in 5 places, 5 issues are generated with file/line information for each usage.

### XML Structure

Validates each window as Kodi loads it, after includes, constants, expressions and defaults are applied.

**Errors:**
- Invalid color, integer, boolean or enumerated values, in tags, attributes and the values of a `$VAR` used there.
- A value that reads as a constant name in a tag or attribute where Kodi substitutes no constants, or one no `<constant>` defines.
- Empty action tags that should use `noop` (e.g., `<onclick></onclick>` instead of `<onclick>noop</onclick>`).
- Empty conditions, and brackets that do not match in a condition or action.
- A condition Kodi cannot parse, or one naming an info Kodi does not have. Kodi reads both as false. A condition naming an `$EXP` that is not defined counts as unparseable.
- A `String.*` or `Integer.*` test whose argument names an info Kodi does not have. Kodi reads that argument as empty text or 0, so `String.IsEmpty(ListItem.Lable)` is always true.
- A dynamic expression such as `$VAR[...]` in a tag that takes its text as written, like `<posx>`. Kodi does not expand it there.
- A second copy of a tag Kodi reads once. Kodi keeps the first and drops the rest. When one of the copies comes from an include, this is a warning.
- A `<defaultcontrol>` whose control can never take focus.
- A missing `]` after `$INFO[`, `$LOCALIZE[` and the like.
- An `$INFO[]` naming an info Kodi does not have, which shows nothing, or only its prefix.
- XML parse errors. Faults Kodi's parser forgives, such as a bare `&`, are reported at their line.
- A window file the targeted Kodi release no longer loads.

**Warnings:**
- Invalid tag: a tag appears where Kodi doesn't read it (e.g., `<label>` directly inside `<window>`), including a `<control>` inside a control that is not a group.
- Invalid attribute: an attribute not recognized for the given tag.
- A tag that sets what the control type's `<default>` already supplies.
- A `<viewtype>` Kodi does not know, or not in lowercase.
- Text beside an include's `<definition>`, which Kodi ignores.
- A `<default type>` written in a case no control uses. Kodi matches it exactly.

When the skin imports an add-on that writes include files at runtime (script.skinshortcuts, script.skinvariables), an undefined `$EXP` or constant name is a warning instead, since the add-on may define it.

`$PARAM[]` works in every tag, since Kodi replaces it while it splices the include.

`<default type="X">` blocks (e.g. in `Defaults.xml`) are validated at their own source against control type X's schema, so a malformed default is reported once at `Defaults.xml` rather than on every control that inherits it, and is never treated as an include warning.

### File Integrity

Checks file encoding, line endings and the files the skin ships.

**Errors:**
- A BOM (byte order mark) at the start of a `.xml`, `.po`, `.txt`, `.py` or `.md` file.
- Windows line endings (`\r\n`) or Mac line endings (`\r`) in any of those files.
- A 16-bit PNG, which TexturePacker cannot pack.
- Two files whose names differ only by case. One overwrites the other on Windows and macOS.
- A string in a `strings.po` that does not close, even where Kodi never reads it, such as the header. Weblate and gettext tools cannot load the file.

**Warnings:** a `strings.po` line with text after its closing quote, such as an unescaped `"` inside the string. Kodi and Weblate still read it; msgfmt rejects the file.

**Warnings (Kodi repo):** a file marked executable, a non-ASCII file name, Python scripts, keymaps, leftovers such as `.bak` or `Thumbs.db`, and context menu items in `addon.xml`. In a git checkout only the files git tracks count.

### Kodi Repo

Checks what the Kodi repo's review tooling checks. Every finding is a warning labeled "Kodi repo".

- `addon.xml`: version, id, extension points, the `xbmc.gui` import and its fit with [`kodi_release`](settings.md#validation), and the add-on schema.
- Artwork named in `addon.xml`: it exists and has an accepted type, size and file size.
- Language folders: named `resource.language.<code>`, with `en_gb` present.
- Each `strings.po`: UTF-8 without a BOM, Kodi's header, no duplicate ids, and it parses.

## Muting a finding

An XML comment mutes findings the skin has already judged. Text after a `;` is the reason:

```xml
<!-- kdk-ignore-file: labels; debug overlay -->   whole file, Labels only
<!-- kdk-ignore: labels, images; add-on name -->   one line, Labels and Images
<!-- kdk-ignore -->                                one line, every check
```

A comment sharing a line with markup covers that line; a comment on a line of its own covers the line below. Check names are the report's categories (`Variables`, `Maps`, `Includes`, `Labels`, `Fonts`, `IDs`, `Images`, `XML Validation`, `File Integrity`, `Kodi Repo`), matched without regard to case, spaces or hyphens.

Comments are read in the XML files of the skin's resolution folders, such as `xml` or `1080i`. A finding in any other file, `addon.xml` and the language files included, cannot be muted.

A file-wide comment needs both the checks it covers and a reason. If either is missing, it mutes nothing and is reported as a warning. A name that matches no check is reported as a warning too; the names it got right still apply.

Muted findings stay out of the on-save phantoms, the results views and the quick panels. The HTML report still lists each one, marked muted with the comment's line and reason, and counts them apart from errors and warnings.

## Settings that affect validation

| Setting | Default | Effect |
|---------|---------|--------|
| [`auto_skin_check`](settings.md#validation) | `true` | Run validation on save |
| [`phantom_severity_level`](settings.md#validation) | `"warning"` | Minimum severity for on-save phantoms |
| [`hide_include_warnings`](settings.md#validation) | `true` | Hide include-originated warnings (phantoms, results view, report) |
| [`validation_exclude`](settings.md#validation) | `["shortcuts"]` | Folder or file names XML Validation skips |
| [`validation_report_directory`](settings.md#validation) | `""` (skin folder) | Where the HTML report is saved |

See [Settings](settings.md) for full details.
