# 4d-plugin-finder-control

Finder Control lets 4D read and write file/folder properties that belong to the macOS Finder — Comments, the Locked flag, the "hide extension" flag, and Finder's own display name/kind/description strings — by driving the Finder application directly through Apple's Cocoa Scripting Bridge (the same mechanism AppleScript uses), rather than manipulating the file's raw extended attributes with a tool like `xattr`. Because the changes are made *through* Finder, they show up immediately in the Get Info panel and are indexed by Spotlight (`mdfind`), which regular `xattr`-based comment tools generally aren't. The plugin also ships one utility command, `Finder SORT ARRAY`, that sorts a text array the same way Finder sorts a file listing (numeric-aware: "File 2" before "File 11"), independent of any actual Finder item.

---

## Commands

| Command | Returns | Purpose |
|---|---|---|
| [`Finder set comment`](#finder-set-comment) | Longint | Set an item's Finder comment |
| [`Finder get comment`](#finder-get-comment) | Longint | Read an item's Finder comment |
| [`Finder set locked`](#finder-set-locked) | Longint | Set an item's locked flag |
| [`Finder get locked`](#finder-get-locked) | Longint | Read an item's locked flag |
| [`Finder set extension hidden`](#finder-set-extension-hidden) | Longint | Show/hide an item's filename extension |
| [`Finder get extension hidden`](#finder-get-extension-hidden) | Longint | Read whether an item's extension is hidden |
| [`Finder SORT ARRAY`](#finder-sort-array) | *(none)* | Sort a text array the way Finder sorts file names |
| [`Finder get display name`](#finder-get-display-name) | Longint | Read the name Finder displays for an item |
| [`Finder get description`](#finder-get-description) | Longint | Read Finder's description string for an item |
| [`Finder get kind`](#finder-get-kind) | Longint | Read Finder's "Kind" string for an item |
| [`Finder reveal`](#finder-reveal) | Longint | Show an item in a Finder window |
| [`Finder trash`](#finder-trash) | Longint | Move an item to the Trash |

**Platforms:** macOS only (Intel and Apple Silicon). Finder has no Windows or Linux equivalent, so this plugin has no build for those platforms.

---

## Manual versioning and publication

Actions has two independent release workflows. **Bump version** takes one required
`mode` choice (`patch`, `minor`, or `major`, default `patch`) and commits source
metadata to the selected branch. It does not build, tag, release, or dispatch
another workflow. **Build** has no custom inputs: select a branch or tag with the
built-in ref selector. It checks out that event's immutable SHA and derives the
canonical `X.Y.Z` version from source, not a tag or an input.

The original Bump header at `267f76ce5fccea99bbfd98585a3c73e5e39687e1`
explicitly coordinates marketing/build/plist versions despite its marketing-only
implementation. The migration keeps intake marketing version `2.0.5`, aligning
the six stale build values and the actual copied `English.lproj/InfoPlist.strings`
short/info display tokens to it. Target and project configurations are
Development, Deployment, and Default (six of each version setting). Source
`Info.plist` retains `$(MARKETING_VERSION)` and its absent build key; prebuilt
bundle metadata is not authority and remains unchanged. Subsequent bumps validate
all source fields before changing any bytes, preserving references, optional build
absence, encodings, line endings, modes, and unrelated content.

Bump requires its committed executable pre-push hook before editing and again
before pushing. It checks the selected branch's advertised old SHA, permits one
nonempty source-only direct-child commit with Actions bot identities and the
co-author trailer, and uses a nonforce push with tag-following disabled. A moved,
deleted, rewound, or already-updated branch stops the run; inspect retained state
rather than retrying blindly.

Build preserves the actual original topology: source validation on Ubuntu, then
macOS Default universal compilation (`arm64` and `x86_64`, deployment override
`11.0`), packaging from `test/Plugins/Finder Control.bundle`, Developer ID signing,
notarization of ZIP and DMG, and DMG stapling. There is no Windows build job:
the existing Windows64 payload, frameworks, static libraries, resources and 4D
project are preserved. Cleanup removes only generated leaves/intermediates, never
the whole bundle or Default siblings. Native tools and credentials are not used
by offline tests.

Publication has constant repository-wide cross-ref concurrency with cancellation
disabled (not a FIFO guarantee). It requires explicit `GH_TOKEN`, unused exact
API/remote tags and no matching draft/published release, checked before native work
and again after signing/notarization/stapling. Final verification retains generated
bytes (including tracked executable/plist/localization, fresh signature and narrow Xcode
intermediates), while checking immutable HEAD, index and raw bytes of all other
tracked files plus unexpected untracked/ignored files. Built XML/binary plist and
localized metadata must match source.

Publication creates a new tag ref at the selected SHA, then a new public release,
then uploads only that new release ID's ZIP and DMG. Original notes policy remains
an empty body with generated notes disabled; GitHub replaces asset-name spaces
with dots. Existing tags/releases are never reused, overwritten, repaired or
deleted. Any failure retains partial tags, releases and assets and reports the
known state: manually inspect the Actions log and repository before deciding
recovery; there is no automated rollback or retry.

Intake `v2.0.5` is already published, so Build on the migrated, unbumped source
intentionally stops at availability checking. Run Bump separately to create a
fresh source version before a later manual Build.

Offline checks: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .github/scripts -v`
and `actionlint .github/workflows/*.yml`.

## Native ownership audit and regression

The bounded audit baseline is `98f16438cfcdacab278942e1523fc5c8842b3357`.
It follows the native ownership guidance at
`miyako/skills@e6b492f:4d-skills/skills/4dplugin/SKILL.md`.
This is not certification in a real 4D host or on Windows.

Tracked native surfaces and reachability:

| Surface | Audit scope |
|---|---|
| `4DPlugin-Finder-Control.cpp/.h` | All 12 selectors and startup; scalar setters/getters, array sorting and comparator, path conversion, platform callbacks and final parameter writes. |
| `4D Plugin API/Classes/C_TEXT.cpp/.h`, `C_LONGINT.cpp/.h`, `ARRAY_TEXT.cpp/.h`, `C_TYPES.h` | Compiled macOS wrappers; borrowed text is copied into C++ storage, scalar output uses the engine content setter, array output creates an independent owner for every slot including index zero. |
| `4D Plugin API/Classes/C_BLOB.cpp/.h` | Dormant first-party byte/hex/base64 wrapper; inspected despite not being in the target. No picture wrapper or native method callback helper is tracked. |
| `support/4DPlugin-JSON.cpp/.h` | Dormant first-party object/picture/string/scalar helpers, owning property getters and synchronous stringify command; not compiled by either project or included by the active plugin. |
| `Finder.h` | Generated ScriptingBridge interfaces, including borrowed platform properties; no SDK string allocation implementation. |
| `4D Plugin API/4DPluginAPI.c/.h`, `PublicTypes.h`, `PrivateTypes.h`, `EntryPoints.h`, `Flags.h`, `.def` | Bundled SDK contract/provenance evidence; engine internals excluded from fixes. `FourDPackex` exports the actual entry, installs the callback and calls `PluginMain`. |
| Xcode project/scheme, Windows solution/project/filters, root and bundled manifests | Xcode compiles main, SDK, C_TEXT, C_LONGINT and ARRAY_TEXT. The legacy Windows list contains only main and SDK, despite macOS-only application code; no Windows build claim. Manifest order matches selectors 1-12; selector 7 is `Finder SORT ARRAY(&Y)`. |
| `include/json/*.h`, `a/libjsoncpp.a`, `lib/windows*/jsoncpp.lib`, prebuilt bundle/archives | Third-party or binary surfaces, unchanged and not used as evidence that source ownership is correct. |

The exact bundled `4DPluginAPI.c` SHA-256 is
`5bac571c5c4cafd280fa7f23d775458a23701287e8735be27d4a2190002f4e3f`
(Git blob `62f745e91d81ef2c3c901c656ea8e175d3b173e8`).
These bytes already exist at
`075bf5ee12eee6664875f26a74c39ad958f1d667:Finder Control/4D Plugin API/4DPluginAPI.c`
and were moved to their current path by
`267f76ce5fccea99bbfd98585a3c73e5e39687e1`.
The historical commit says "bump to v18", while file comments say v14/v13;
none establishes a verified upstream SDK release identity. Upstream GitHub
API access required organization SSO during this audit. No SDK engine or
contract headers are rewritten.

The bundled array setter accepts only Unicode arrays with non-null storage,
`0 <= index <= fNbElements`, and a non-null input descriptor. Accepted
assignments dispose the old element and shallow-transfer the new descriptor;
rejections leave the caller owning its string. Getter descriptors are borrowed.
The array wrapper now rejects missing storage before allocating output strings
or publishing a newly created array type. Ordinary copy/replace/shrink/clear
behavior and index-zero handling are preserved.

Four dormant JSON string setter overloads and the picture setter now initialize
an Undefined destination before shallow assignment, avoiding overwritten empty
owners. Picture/object/collection setters retain their existing consuming
handoff contract; callers must not dispose an already-consumed input. Successful
property getters return owning variables: scalar helpers copy then clear them,
including mismatches; successful object/collection helpers hand ownership to the
caller, who must use `PA_DisposeObject`/`PA_DisposeCollection`. Failed getters
are checked before any inspection, adoption or cleanup of their output.
Stringify clears its owning return after conversion, but never reads/clears the
SDK's invalid raw-kind-zero command-handle-failure sentinel. Errors are logged
before the existing failure-shaped return. Borrowed synchronous SDK command
inputs remain borrowed; `PA_ReturnString` is a content setter, not an array transfer.

Run the unsigned macOS regression with an existing dedicated scratch directory:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tests/native/run.py --workdir "$ARTIFACTS"
```

For comparison, export the baseline with `git archive` into a separate directory
under the same scratch area and run the **same current runner/harness** with
`--source "$BASELINE" --workdir "$ARTIFACTS"`. The runner compiles actual production
sources and the full unchanged SDK, not extracted API snippets. ASan/UBSan are
enabled; macOS LeakSanitizer is unavailable, so strings, handles, pictures and
object/collection reference counts have explicit final balance assertions.
Exact ASCII, BMP, supplementary and empty text is checked with both allocated
and null empty strings, exact UTF-16 allocation/termination and UTF-8 bytes.
Coverage includes replacement, copied borrowed inputs, independent array
transfers, shrink/clear, rejected destinations/creation, successful owning
handoff survival, poisoned failed outputs, scalar return copies and command
failure sentinels. SDK resize-OOM count corruption is not certified by normal
array tests and remains out of scope.

On macOS arm64 with Apple Clang 21, the unchanged final harness passes all 32
case/empty-representation combinations on the fix. Against the immutable
baseline it fails 23 combinations: overwritten empty owners, owning getter
results/mismatches, all five failed getter outputs, raw-zero command sentinels,
and rejected/missing array storage. Ordinary array transfers, scalar return
copies, successful stringify cleanup and the stubbed dispatcher pass on both.

The exported dispatcher is invoked only after replacing ScriptingBridge with
test-only classes and defining stub AppleEvent/permission functions. Even
startup, reveal and trash operate exclusively on synthetic objects: no Finder,
desktop, windows, preferences, private files or real permission prompts.
No release configuration, signing, notarization, packaging, manual workflow
dispatch, binary replacement or publication is part of this regression.
Ambiguous SDK-only application-path/picture-data/pointer ownership and engine
internals are deferred; no blanket disposal deletion or unrelated algorithm
hardening is included.

## Requirements & platform notes

- **macOS 10.14 (Mojave) or later.** The plugin checks Automation permission at startup using an API only available from macOS 10.14 onward.
- **Automation permission is required the first time any command actually talks to Finder.** macOS will show a system dialog ("*4D* wants access to control 'Finder'") the first time a command like `Finder get comment` or `Finder reveal` runs. Until that's approved, those calls fail (return `0`) rather than raising a 4D error. If it's ever denied, or needs to be re-granted, the switch is under **System Settings → Privacy & Security → Automation**.
- **Every command works on a single filesystem path.** The `path` parameter must be a valid platform (POSIX) path to a file or folder that exists on disk *at the moment of the call*. If Finder can't resolve it, the command's `Result` is `0` and no property is read or changed. The plugin's own test method builds this path from a `Folder` object's `platformPath` property — see the examples below.
- **All commands are marked thread-safe in the plugin's manifest** and may run on a 4D worker process rather than the main process.
- **`Finder SORT ARRAY` is the one exception to the pattern above** — it doesn't touch Finder or the filesystem at all, and it has no `Result`/return value (see its own section below).
- *As of the currently reviewed/fixed build:* if Finder is unresponsive, or Automation permission hasn't been granted yet, every command now reliably returns `0` rather than potentially leaving the call hanging — this is a robustness property of this specific build, not something to assume of every historical release of the plugin.

---

## Finder set comment

### Syntax

```4d
Finder set comment ( path : Text ; comment : Text ) → Longint
```

| Parameter | Type | Description |
|---|---|---|
| `path` | Text | Platform path to the file or folder |
| `comment` | Text | The comment text to store |
| Result | Longint | `1` if the comment was set, `0` otherwise |

### Description

Sets the item's **Comments** field, exactly as it appears in the Finder's Get Info panel. Because the write happens through Finder itself (not by writing an extended attribute directly), the new comment is picked up by Spotlight/`mdfind` immediately.

An empty string is a valid comment — passing `""` clears any existing comment. The command has no effect, and returns `0`, if `path` doesn't resolve to an existing Finder item.

### Example

```4d
//from the plugin's own README
$path:=Get 4D folder(Current Resources folder)+"sample.png"
$success:=Finder set comment ($path;"some comment")
```

```4d
//clearing a comment
$success:=Finder set comment ($path;"")
```

---

## Finder get comment

### Syntax

```4d
Finder get comment ( path : Text ; comment : Text ) → Longint
```

| Parameter | Type | Description |
|---|---|---|
| `path` | Text | Platform path to the file or folder |
| `comment` | Text | *(output)* the item's current comment |
| Result | Longint | `1` if the comment was read, `0` otherwise |

### Description

Reads the item's Finder **Comments** field back into `comment`. If the item has no comment set — the normal, default state for most files — `comment` is set to an empty string; this is not treated as a failure as long as the item itself was found (`Result` is still `1`).

If `path` doesn't resolve to an existing item, `comment` is left untouched and `Result` is `0`.

### Example

```4d
//from the plugin's own README
$path:=Get 4D folder(Current Resources folder)+"sample.png"
$success:=Finder get comment ($path;$comment)
```

---

## Finder set locked

### Syntax

```4d
Finder set locked ( path : Text ; locked : Longint ) → Longint
```

| Parameter | Type | Description |
|---|---|---|
| `path` | Text | Platform path to the file or folder |
| `locked` | Longint | `1` to lock the item, `0` to unlock it |
| Result | Longint | `1` if the flag was set, `0` otherwise |

### Description

Sets the item's **Locked** checkbox, exactly as shown in the Get Info panel. A locked item can't be renamed, edited, or moved to the Trash by Finder — including by [`Finder trash`](#finder-trash) below — so unlock an item first if you intend to trash it afterward.

### Example

```4d
//from the plugin's own README
$path:=Get 4D folder(Current Resources folder)+"sample.png"
$success:=Finder set locked ($path;1)
```

```4d
//unlock before trashing (from the plugin's own README)
$success:=Finder set locked ($temp;0)
$success:=Finder trash ($temp)
```

---

## Finder get locked

### Syntax

```4d
Finder get locked ( path : Text ; locked : Longint ) → Longint
```

| Parameter | Type | Description |
|---|---|---|
| `path` | Text | Platform path to the file or folder |
| `locked` | Longint | *(output)* `1` if the item is locked, `0` if not |
| Result | Longint | `1` if the flag was read, `0` otherwise |

### Description

Reads the item's current **Locked** state into `locked`. If `path` doesn't resolve to an existing item, `locked` is left untouched and `Result` is `0`.

### Example

```4d
//from the plugin's own README
$success:=Finder get locked ($path;$locked)
```

---

## Finder set extension hidden

### Syntax

```4d
Finder set extension hidden ( path : Text ; extensionHidden : Longint ) → Longint
```

| Parameter | Type | Description |
|---|---|---|
| `path` | Text | Platform path to the file or folder |
| `extensionHidden` | Longint | `1` to hide the filename extension, `0` to show it |
| Result | Longint | `1` if the flag was set, `0` otherwise |

### Description

Sets the **Hide extension** checkbox in Get Info, controlling whether Finder shows the item's filename extension (e.g. `sample.png` vs. `sample`) in windows, dialogs, and the Finder display name. This only affects how Finder *displays* the name — it never renames the file on disk.

### Example

```4d
//from the plugin's own README
$success:=Finder set extension hidden ($path;1)
```

---

## Finder get extension hidden

### Syntax

```4d
Finder get extension hidden ( path : Text ; extensionHidden : Longint ) → Longint
```

| Parameter | Type | Description |
|---|---|---|
| `path` | Text | Platform path to the file or folder |
| `extensionHidden` | Longint | *(output)* `1` if the extension is hidden, `0` if shown |
| Result | Longint | `1` if the flag was read, `0` otherwise |

### Description

Reads whether the item's filename extension is currently hidden in Finder. If `path` doesn't resolve to an existing item, `extensionHidden` is left untouched and `Result` is `0`.

### Example

```4d
//from the plugin's own README
$success:=Finder get extension hidden ($path;$extensionHidden)
```

---

## Finder SORT ARRAY

### Syntax

```4d
Finder SORT ARRAY ( array : Text array )
```

| Parameter | Type | Description |
|---|---|---|
| `array` | Text array | The array to sort, modified in place |

### Description

Sorts `array` in place using the same case-insensitive, locale-aware, **numeric-aware** ordering Finder uses to sort a file listing — so `"File 2"` sorts before `"File 11"`, unlike a plain alphabetical sort where `"File 11"` would come first. This command doesn't touch Finder, the filesystem, or any real file at all; it's a pure utility for sorting names the same way Finder would, useful when you're building your own file listing UI.

Unlike every other command in this plugin, **`Finder SORT ARRAY` has no `Result` and no return value at all** — check your array's contents directly rather than testing a success flag.

### Example

```4d
//from the plugin's own README
ARRAY TEXT($test;5)

$test{0}:="test 1"
$test{1}:="test 11"
$test{2}:="test 10"
$test{3}:="test 2"
$test{4}:="test 21"
$test{5}:="test 20"

Finder SORT ARRAY ($test)
//$test is now: test 1, test 2, test 10, test 11, test 20, test 21
```

---

## Finder get display name

### Syntax

```4d
Finder get display name ( path : Text ; displayName : Text ) → Longint
```

| Parameter | Type | Description |
|---|---|---|
| `path` | Text | Platform path to the file or folder |
| `displayName` | Text | *(output)* the name Finder displays for the item |
| Result | Longint | `1` if the name was read, `0` otherwise |

### Description

Reads the name Finder actually *displays* for the item, which can differ from the item's raw filename — for example, when the extension is hidden (see [`Finder set extension hidden`](#finder-set-extension-hidden) above), or on a localized system where Finder substitutes a localized name for certain system folders. If `path` doesn't resolve to an existing item, `displayName` is left untouched and `Result` is `0`.

### Example

```4d
//from the plugin's own README
$success:=Finder get display name ($path;$displayName)
```

---

## Finder get description

### Syntax

```4d
Finder get description ( path : Text ; description : Text ) → Longint
```

| Parameter | Type | Description |
|---|---|---|
| `path` | Text | Platform path to the file or folder |
| `description` | Text | *(output)* Finder's description string for the item |
| Result | Longint | `1` if the description was read, `0` otherwise |

### Description

This is a **read-only** property — the plugin exposes no corresponding "set" command. It reads Finder's own descriptive text for the item, separate from the shorter "Kind" string (see [`Finder get kind`](#finder-get-kind) below). The exact wording Finder returns here depends on macOS's system-wide file-type metadata (UTIs and installed Spotlight importers), so it can vary between macOS versions and installed software — treat it as a human-readable label rather than a fixed, machine-parseable value. If `path` doesn't resolve to an existing item, `description` is left untouched and `Result` is `0`.

### Example

```4d
//from the plugin's own README
$success:=Finder get description ($path;$description)
```

---

## Finder get kind

### Syntax

```4d
Finder get kind ( path : Text ; kind : Text ) → Longint
```

| Parameter | Type | Description |
|---|---|---|
| `path` | Text | Platform path to the file or folder |
| `kind` | Text | *(output)* Finder's "Kind" string for the item |
| Result | Longint | `1` if the kind was read, `0` otherwise |

### Description

This is a **read-only** property. It reads the short type label Finder shows in the "Kind" column of a list view and in Get Info — for example `"Folder"`, `"Application"`, or a document-type description such as `"Rich Text Document"`. As with [`Finder get description`](#finder-get-description), the exact string comes from macOS's system-wide file-type metadata and can vary by macOS version or installed software. If `path` doesn't resolve to an existing item, `kind` is left untouched and `Result` is `0`.

### Example

```4d
//from the plugin's own README
$success:=Finder get kind ($path;$kind)
```

---

## Finder reveal

### Syntax

```4d
Finder reveal ( path : Text ) → Longint
```

| Parameter | Type | Description |
|---|---|---|
| `path` | Text | Platform path to the file or folder |
| Result | Longint | `1` if the item was revealed, `0` otherwise |

### Description

Brings Finder to the front and shows the item selected in a Finder window — equivalent to Finder's own "Show in Finder" behavior. If `path` doesn't resolve to an existing item, `Result` is `0` and nothing happens.

### Example

```4d
//from the plugin's own README
$success:=Finder reveal ($path)
```

---

## Finder trash

### Syntax

```4d
Finder trash ( path : Text ) → Longint
```

| Parameter | Type | Description |
|---|---|---|
| `path` | Text | Platform path to the file or folder |
| Result | Longint | `1` if the item was moved to the Trash, `0` otherwise |

### Description

Moves the item to the Trash through Finder — this is the same as dragging it to the Trash or pressing ⌘⌫ in Finder, **not** a permanent delete. If the item is [locked](#finder-set-locked), Finder will refuse to trash it and `Result` is `0`; unlock it first with `Finder set locked` and a `locked` value of `0`. `Result` is also `0` if `path` doesn't resolve to an existing item.

### Example

From the plugin's own test method (`TEST.4dm`):

```4d
//%attributes = {}
$file:=Folder(fk desktop folder).file("test")
$file.setText("aaaa")
$path:=$file.platformPath

$success:=Finder trash ($path)
```

A second example, from the plugin's own README, showing the unlock-then-trash pattern:

```4d
$temp:=System folder(Desktop)+Generate UUID
COPY DOCUMENT($path;$temp)

//move to trash
$success:=Finder set locked ($temp;0)
$success:=Finder trash ($temp)
```

---

## Error handling & troubleshooting

- **`Result` is `0` whenever Finder can't locate the item.** This applies to every command in this plugin except `Finder SORT ARRAY` — if `path` doesn't point to a file or folder that exists at the moment of the call, the command does nothing and returns `0` rather than raising a 4D error.
- **The very first Automation permission prompt gates everything.** The first time any command in this plugin actually talks to Finder, macOS shows a system dialog asking to approve automation access. Until it's approved, calls silently fail (`Result` is `0`). If commands unexpectedly return `0` right after installing the plugin, or on a freshly reset machine, check **System Settings → Privacy & Security → Automation** before assuming anything else is wrong.
- **A locked item can't be trashed (or renamed/edited) by Finder.** If [`Finder trash`](#finder-trash) returns `0` on an item you expect to exist, check whether it's locked and clear the flag first with [`Finder set locked`](#finder-set-locked).
- **An empty comment is normal, not an error.** [`Finder get comment`](#finder-get-comment) returns an empty string (with `Result` still `1`) for any item that simply has no comment set — that's the default state of most files, not a failure signal.
- **`Finder SORT ARRAY` has no `Result` at all.** Don't write code that checks a success flag for it — check the array's contents directly if you need to confirm it worked.
- **`Finder get kind` and `Finder get description` return macOS-supplied labels, not stable identifiers.** Their exact wording depends on system-wide file-type metadata (UTIs, Spotlight importers) and can differ across macOS versions or installed software — don't build logic that pattern-matches their exact text without allowing for that variation.

---

## Quick reference

```4d
$path:=Get 4D folder(Current Resources folder)+"sample.png"

//comments as displayed in the Get Info dialog
$success:=Finder set comment ($path;"some comment")
$success:=Finder get comment ($path;$comment)

$success:=Finder set extension hidden ($path;1)
$success:=Finder get extension hidden ($path;$extensionHidden)

//the locked attribute as displayed in the Get Info dialog
$success:=Finder set locked ($path;1)
$success:=Finder get locked ($path;$locked)

//read-only properties
$success:=Finder get description ($path;$description)
$success:=Finder get display name ($path;$displayName)
$success:=Finder get kind ($path;$kind)

//show in Finder
$success:=Finder reveal ($path)

//move to trash (unlock first if needed)
$success:=Finder set locked ($path;0)
$success:=Finder trash ($path)

//sort like Finder
ARRAY TEXT($test;5)
$test{0}:="test 1"
$test{1}:="test 11"
$test{2}:="test 10"
$test{3}:="test 2"
$test{4}:="test 21"
$test{5}:="test 20"
Finder SORT ARRAY ($test)
```
