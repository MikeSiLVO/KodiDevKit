# Skin Shortcuts integration

## What is Skin Shortcuts?

[script.skinshortcuts](https://github.com/MikeSiLVO/script.skinshortcuts) is a Kodi addon that generates menu XML at runtime. Skins define a template file in `shortcuts/`, and the addon fills it with user-configured menu entries at startup, producing files like `script-skinshortcuts-includes.xml`.

This means some includes, variables, and XML structures only exist at runtime and cannot be statically validated. KodiDevKit detects Skin Shortcuts usage and adjusts validation accordingly.

## What KodiDevKit reads

1. **The `shortcuts/` folder**: Every XML file in it is read for references to the skin's variables and maps. The files themselves are not validated (see the end of this page).

2. **The template**: `shortcuts/templates.xml` (v3), else `shortcuts/template.xml` (v2). Its include references count as used, and the variables it declares count as defined.

3. **addon.xml**: When the skin imports `script.skinshortcuts` or `script.skinvariables`, an undefined `$EXP` or constant name is a warning instead of an error, since the add-on may write it at runtime.

## v2 vs v3

| | v2 | v3 |
|---|---|---|
| Template file | `shortcuts/template.xml` | `shortcuts/templates.xml` |
| Override files | `shortcuts/overrides.xml` | Split across multiple files |
| Include syntax | `<include>Name</include>` | `<include content="Name">` and `<skinshortcuts include="Name">` |

KodiDevKit checks for v3 first (`templates.xml`), then falls back to v2 (`template.xml`).

## What KodiDevKit marks as used

These references count as "used" (preventing false unused reports):

- **`$VAR[Name]` / `$ESCVAR[Name]`** in text and attribute values of any file in `shortcuts/` marks the variable as used.
- **`$MAP[...]`** in any file in `shortcuts/` marks the map as used.
- **`<include>Name</include>`** tags and **`content="Name"` / `include="Name"` attributes** in the template marks the include as used.

## What KodiDevKit skips

These are runtime placeholders that cannot be resolved statically:

- **`$SKINSHORTCUTS[...]`**: Skin Shortcuts runtime values (menu labels, paths, etc.).
- **`$PROPERTY[...]`**: Dynamic property values set at runtime.

Any variable or include reference containing these placeholders is ignored during validation.

## Runtime include names

Include references matching these patterns are never reported as undefined, whatever the skin imports:

| Pattern | Example | Source |
|---------|---------|--------|
| `skinshortcuts-*` | `skinshortcuts-mainmenu` | script.skinshortcuts |
| `skinvariables-*` | `skinvariables-colorset` | script.skinvariables |
| `script-*-includes` | `script-skinshortcuts-includes` | Add-ons that write include files |

A missing `<include file="script-*-includes.xml">` is not reported either.

## Generated files

- **`script-skinshortcuts-includes.xml`**: Left out of the label, ID, font and image checks, since its content is generated at runtime. When it exists, the includes it defines count as defined.
- **`script-skinvariables-*` files**: Issues inside them are not reported.

## Excluded from validation

The `shortcuts/` folder is in the default [`validation_exclude`](settings.md#validation) list, so template files themselves are not validated for XML structure issues.
