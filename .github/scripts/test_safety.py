"""Offline safety regressions: real local Git, closed command paths, and synthetic GitHub."""

import contextlib
import importlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import unittest
import uuid


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / ".github/scripts"
PINNED = "6b6e582d6506ea2bc5b39574c674aa3d744aca88"
PRODUCT = "Finder Control"
REPO = "miyako/4d-plugin-finder-control"
PROJECT = Path("Finder Control.xcodeproj/project.pbxproj")
PLIST = Path("Info.plist")
LOCALIZED = Path("English.lproj/InfoPlist.strings")
SOURCE_PATHS = (PROJECT, PLIST, LOCALIZED)
BUNDLE = Path("test/Plugins/Finder Control.bundle")
TRAILER = "Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
REAL_GIT = shutil.which("git")
GIT_EXEC = Path(subprocess.check_output([REAL_GIT, "--exec-path"], text=True).strip())


def setUpModule():
    sys.path.insert(0, str(SCRIPTS))
    global source_version, repository, native, release, bump
    source_version, repository, native, release, bump = (
        importlib.import_module(name)
        for name in ("source_version", "repository", "native", "release", "bump")
    )


@contextlib.contextmanager
def working_directory(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class Fixture(unittest.TestCase):
    def setUp(self):
        # Deliberately do not use tempfile: all disposable state lives under this checkout.
        self.scratch = ROOT / ".github/scripts" / (".safety-" + uuid.uuid4().hex)
        self.scratch.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.scratch)
        self.root = self.scratch / "checkout"
        self.root.mkdir()
        self.original = {path: (ROOT / path).read_bytes() for path in SOURCE_PATHS}
        for path, data in self.original.items():
            self.write(path, data)
        self.version = source_version.read(self.root)

    def write(self, path, data=b"fixture"):
        path = self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def replace(self, path, old, new, count=-1):
        target = self.root / path
        value, encoding, bom = source_version.decode(target.read_bytes())
        self.assertIn(old, value)
        target.write_bytes(bom + value.replace(old, new, count).encode(encoding))

    def inspect(self):
        return source_version.read(self.root)

    def assertInvalid(self):
        with self.assertRaises((ValueError, UnicodeError)):
            self.inspect()

    def built(self, fmt=plistlib.FMT_XML, localized_format="strings"):
        value = dict(source_version.load_plist((self.root / PLIST).read_bytes()))
        for key in (source_version.SHORT, source_version.BUILD):
            if key in value:
                value[key] = self.version
        self.write(BUNDLE / "Contents/Info.plist", plistlib.dumps(value, fmt=fmt))
        fields = source_version.localized_fields(source_version.text(self.root / LOCALIZED))
        localized = {key: (self.version if field[0] in source_version.REFERENCES else field[0])
                     for key, field in fields.items()}
        path = BUNDLE / "Contents/Resources" / LOCALIZED
        if localized_format == "strings":
            data = "\n".join(f'{key} = "{value}";' for key, value in localized.items()).encode()
        else:
            data = plistlib.dumps(localized, fmt=localized_format)
        self.write(path, data)
        self.write(BUNDLE / f"Contents/MacOS/{PRODUCT}", b"synthetic executable\0")

    def verify_built(self):
        source_version.verify_bundle(self.root / BUNDLE, self.root)


class SourceSafetyTests(Fixture):
    def test_current_source_contract_is_dynamic(self):
        self.assertRegex(self.version, r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
        fields = source_version.project_settings(source_version.text(self.root / PROJECT))
        self.assertEqual({key: len(value) for key, value in fields.items()},
                         {"MARKETING_VERSION": 6, "CURRENT_PROJECT_VERSION": 6})
        value = source_version.load_plist(self.original[PLIST])
        self.assertEqual(value["CFBundleShortVersionString"], "$(MARKETING_VERSION)")
        self.assertNotIn("CFBundleVersion", value)
        localized = source_version.localized_fields(source_version.text(self.root / LOCALIZED))
        self.assertEqual(localized["CFBundleShortVersionString"][0], self.version)
        self.assertEqual(localized["CFBundleGetInfoString"][0],
                         f"Finder Control version {self.version}, Copyright 2021 miyako.")

    def test_pinned_original_intake_is_not_silently_rewritten(self):
        data = {}
        for path in SOURCE_PATHS:
            data[path] = subprocess.check_output(
                [REAL_GIT, "show", f"{PINNED}:{path}"], cwd=ROOT)
        fields = source_version.project_settings(source_version.decode(data[PROJECT])[0])
        self.assertEqual([len(fields[key]) for key in source_version.KEYS], [6, 6])
        self.assertNotIn("CFBundleVersion", source_version.load_plist(data[PLIST]))
        localized = source_version.localized_fields(source_version.decode(data[LOCALIZED])[0])
        self.assertEqual(localized["CFBundleShortVersionString"][0], "2.0.2")
        self.assertEqual(localized["CFBundleGetInfoString"][0],
                         "Finder Control version 2.0.2, Copyright 2021 miyako.")
        with self.assertRaises(ValueError):
            source_version.inspect_data(data)

    def test_patch_minor_major_are_coordinated(self):
        numbers = list(map(int, self.version.split(".")))
        for mode, index in (("patch", 2), ("minor", 1), ("major", 0)):
            with self.subTest(mode=mode):
                for path, data in self.original.items():
                    self.write(path, data)
                expected = numbers[:]
                expected[index] += 1
                expected[index + 1:] = [0] * (2 - index)
                version = ".".join(map(str, expected))
                self.assertEqual(source_version.bump(mode, self.root), version)
                self.assertEqual(self.inspect(), version)
                self.assertEqual((self.root / PLIST).read_bytes(), self.original[PLIST])

    def test_all_encodings_mixed_endings_modes_and_exact_spans(self):
        for encoding, bom in (
            ("utf-8", b""), ("utf-8", b"\xef\xbb\xbf"),
            ("utf-16-le", b"\xff\xfe"), ("utf-16-be", b"\xfe\xff"),
            ("utf-16-le", b""), ("utf-16-be", b""),
        ):
            with self.subTest(encoding=encoding, bom=bom):
                originals = {}
                for index, (path, data) in enumerate(self.original.items()):
                    value = source_version.decode(data)[0]
                    value = value.replace("\r\n", "\n").replace("\r", "\n")
                    value = "".join(line + ("\r\n", "\r", "\n")[i % 3]
                                    for i, line in enumerate(value.splitlines()))
                    # Preserve the XML encoding declaration while changing actual serialization.
                    if path == PLIST and encoding.startswith("utf-16"):
                        value = value.replace('encoding="UTF-8"', 'encoding="UTF-16"')
                    raw = bom + value.encode(encoding)
                    target = self.write(path, raw)
                    target.chmod(0o755 if index % 2 else 0o644)
                    originals[path] = (raw, target.stat().st_mode)
                _, edits = source_version.inspect(self.root)
                new = source_version.bump("patch", self.root)
                for path, (raw, mode) in originals.items():
                    value, codec, marker = source_version.decode(raw)
                    for start, end in sorted(edits[path], reverse=True):
                        value = value[:start] + new + value[end:]
                    target = self.root / path
                    self.assertEqual(target.read_bytes(), marker + value.encode(codec))
                    self.assertEqual(target.stat().st_mode, mode)

    def test_project_comment_noise_and_quoted_keys_same_line(self):
        text = source_version.text(self.root / PROJECT)
        text = re.sub(r"\b(MARKETING_VERSION|CURRENT_PROJECT_VERSION)\s*=",
                      r'"\1" =', text)
        text = re.sub(r"//[^\r\n]*", "", text).replace("\n", " ")
        text += (' /* MARKETING_VERSION = 9.9.9; CURRENT_PROJECT_VERSION = 9.9.9; */'
                 '\n// MARKETING_VERSION = 8.8.8;\n')
        self.write(PROJECT, text.encode())
        self.assertEqual(self.inspect(), self.version)
        source_version.bump("minor", self.root)

    def test_duplicate_quoted_unquoted_project_key_rejected_atomically(self):
        text = source_version.text(self.root / PROJECT)
        text = text.replace("CURRENT_PROJECT_VERSION =", '"MARKETING_VERSION" = "9.9.9"; '
                            "CURRENT_PROJECT_VERSION =", 1)
        self.write(PROJECT, text.encode())
        before = {path: (self.root / path).read_bytes() for path in SOURCE_PATHS}
        with self.assertRaises(ValueError):
            source_version.bump("patch", self.root)
        self.assertEqual(before, {path: (self.root / path).read_bytes() for path in SOURCE_PATHS})

    def test_reference_aliases_are_preserved(self):
        for reference in ("$(MARKETING_VERSION)", "${MARKETING_VERSION}"):
            with self.subTest(reference=reference):
                for path, data in self.original.items():
                    self.write(path, data)
                text = source_version.text(self.root / PROJECT)
                text = re.sub(r"(CURRENT_PROJECT_VERSION\s*=\s*)[^;]+;",
                              lambda match: match[1] + '"' + reference + '";', text)
                self.write(PROJECT, text.encode())
                self.assertEqual(self.inspect(), self.version)
                source_version.bump("patch", self.root)
                self.assertEqual(source_version.text(self.root / PROJECT).count(reference), 6)

    def test_cycles_and_unknown_references_rejected(self):
        original = self.original[PROJECT]
        for market, build in (("$(CURRENT_PROJECT_VERSION)", "$(MARKETING_VERSION)"),
                              ("$(NO_SUCH_SETTING)", self.version)):
            with self.subTest(market=market):
                text = source_version.decode(original)[0]
                for key, value in (("MARKETING_VERSION", market),
                                   ("CURRENT_PROJECT_VERSION", build)):
                    text = re.sub(rf"({key}\s*=\s*)[^;]+;",
                                  lambda match: match[1] + '"' + value + '";', text)
                self.write(PROJECT, text.encode())
                self.assertInvalid()

    def test_project_drift_counts_and_configuration_pairing_rejected(self):
        for transformation in (
            lambda text: re.sub(r"(MARKETING_VERSION\s*=\s*)[^;]+;",
                                r"\g<1>99.99.99;", text, count=1),
            lambda text: re.sub(r"MARKETING_VERSION\s*=\s*[^;]+;", "", text, count=1),
            lambda text: text + f"\n{{ MARKETING_VERSION = {self.version}; "
                                f"CURRENT_PROJECT_VERSION = {self.version}; }}",
            lambda text: text + "\n}",
            lambda text: text + "\n/* unterminated",
            lambda text: re.sub(r"CURRENT_PROJECT_VERSION\s*=\s*[^;]+;", "", text, count=1)
            + f"\n{{ CURRENT_PROJECT_VERSION = {self.version}; }}",
        ):
            with self.subTest(transformation=transformation):
                self.write(PROJECT, transformation(
                    source_version.decode(self.original[PROJECT])[0]).encode())
                self.assertInvalid()

    def test_noncanonical_versions_rejected(self):
        for bad in ("01.2.3", "1.02.3", "1.2", "1.2.3.4", "1.2.3-beta", "-1.2.3"):
            with self.subTest(bad=bad):
                text = source_version.decode(self.original[PROJECT])[0]
                text = re.sub(r"((?:MARKETING_VERSION|CURRENT_PROJECT_VERSION)\s*=\s*)[^;]+;",
                              lambda match: match[1] + '"' + bad + '";', text)
                self.write(PROJECT, text.encode())
                self.assertInvalid()

    def test_source_plist_short_required_optional_build_validated(self):
        value = dict(source_version.load_plist(self.original[PLIST]))
        value["CFBundleVersion"] = "$(CURRENT_PROJECT_VERSION)"
        self.write(PLIST, plistlib.dumps(value))
        self.assertEqual(self.inspect(), self.version)
        value["CFBundleVersion"] = "9.8.7"
        self.write(PLIST, plistlib.dumps(value))
        self.assertInvalid()
        del value["CFBundleShortVersionString"]
        self.write(PLIST, plistlib.dumps(value))
        self.assertInvalid()

    def test_duplicate_plist_and_localized_keys_rejected(self):
        self.replace(PLIST, "</dict>",
                     "<key>CFBundleShortVersionString</key><string>$(MARKETING_VERSION)</string>"
                     "</dict>")
        self.assertInvalid()
        self.write(PLIST, self.original[PLIST])
        value = source_version.text(self.root / LOCALIZED)
        self.write(LOCALIZED, (value + '\n"CFBundleShortVersionString" = "' +
                               self.version + '";').encode())
        self.assertInvalid()

    def test_localized_required_information_and_optional_build(self):
        original = source_version.decode(self.original[LOCALIZED])[0]
        for value in (
            original.replace(f"version {self.version}", "version 99.0.0"),
            re.sub(r"CFBundleShortVersionString\s*=\s*[^;]+;", "", original),
            re.sub(r"CFBundleGetInfoString\s*=\s*[^;]+;", "", original),
            original + '\nCFBundleVersion = "1.0.0";',
            original + "\nnot valid syntax",
        ):
            with self.subTest(value=value):
                self.write(LOCALIZED, value.encode())
                self.assertInvalid()
        self.write(LOCALIZED, (original + '\nCFBundleVersion = "$(CURRENT_PROJECT_VERSION)";').encode())
        self.assertEqual(self.inspect(), self.version)

    def test_malformed_encoding_rejected(self):
        for raw in (b"\xff", b"\0a\0", b"a\0\0a", b"\xef\xbb\xbf\0"):
            with self.subTest(raw=raw):
                self.write(LOCALIZED, raw)
                self.assertInvalid()

    def test_built_xml_binary_and_all_localization_serializations(self):
        for fmt in (plistlib.FMT_XML, plistlib.FMT_BINARY):
            for localized in ("strings", plistlib.FMT_XML, plistlib.FMT_BINARY):
                with self.subTest(fmt=fmt, localized=localized):
                    self.built(fmt, localized)
                    self.verify_built()

    def test_built_version_presence_drift_and_duplicate_metadata_rejected(self):
        for value in (
            {"CFBundleShortVersionString": "9.9.9"},
            {"CFBundleShortVersionString": self.version, "CFBundleVersion": self.version},
            {},
            [],
        ):
            with self.subTest(value=value):
                self.built()
                self.write(BUNDLE / "Contents/Info.plist", plistlib.dumps(value))
                with self.assertRaises(ValueError):
                    self.verify_built()
        self.built()
        self.write(BUNDLE / "Contents/Resources" / LOCALIZED,
                   f'CFBundleShortVersionString = "{self.version}";'.encode())
        with self.assertRaises(ValueError):
            self.verify_built()

    def test_native_configuration_names_are_validated_not_just_counts(self):
        original = source_version.decode(self.original[PROJECT])[0]
        for value in (
            original.replace("name = Development;", "name = Other;", 1),
            original.replace("name = Development;", "name = Default;", 1),
            original.replace("isa = XCBuildConfiguration;", "isa = Other;", 1),
            original.replace("isa = XCBuildConfiguration;",
                             "isa = XCBuildConfiguration; name = Other;", 1),
        ):
            with self.subTest(value=value):
                self.write(PROJECT, value.encode())
                self.assertInvalid()

    def test_extra_native_configuration_without_versions_is_rejected(self):
        value = source_version.text(self.root / PROJECT)
        value = value.replace("objects = {", """
objects = {
    ABCDEF0123456789ABCDEF01 = {
        isa = XCBuildConfiguration;
        buildSettings = {};
        name = Default;
    };
""", 1)
        self.write(PROJECT, value.encode())
        with self.assertRaisesRegex(ValueError, "Every native configuration"):
            self.inspect()

    def test_optional_source_and_localized_build_fields_resolve_in_built_bundle(self):
        value = dict(source_version.load_plist(self.original[PLIST]))
        value["CFBundleVersion"] = "$(CURRENT_PROJECT_VERSION)"
        self.write(PLIST, plistlib.dumps(value))
        value = source_version.text(self.root / LOCALIZED)
        self.write(LOCALIZED, (value + '\nCFBundleVersion = "$(CURRENT_PROJECT_VERSION)";').encode())
        self.built(plistlib.FMT_BINARY, plistlib.FMT_BINARY)
        self.verify_built()
        built = self.root / BUNDLE / "Contents/Info.plist"
        value = dict(source_version.load_plist(built.read_bytes()))
        del value["CFBundleVersion"]
        built.write_bytes(plistlib.dumps(value))
        with self.assertRaises(ValueError):
            self.verify_built()

    def test_built_duplicate_localized_and_plist_keys_rejected(self):
        self.built()
        path = BUNDLE / "Contents/Resources" / LOCALIZED
        original = (self.root / path).read_bytes()
        self.write(path, original + f'\n"CFBundleShortVersionString" = "{self.version}";'.encode())
        with self.assertRaises(ValueError):
            self.verify_built()
        self.built()
        path = BUNDLE / "Contents/Info.plist"
        self.replace(path, "</dict>",
                     f"<key>CFBundleShortVersionString</key><string>{self.version}</string></dict>")
        with self.assertRaises(ValueError):
            self.verify_built()

    def test_generated_classifier_has_exact_directory_boundaries(self):
        for path in (f"{BUNDLE}/Contents/MacOS/{PRODUCT}", f"{BUNDLE}/Contents/Info.plist",
                     f"{BUNDLE}/Contents/Resources/English.lproj/InfoPlist.strings",
                     f"{BUNDLE}/Contents/_CodeSignature/CodeResources",
                     "build/XCBuildData/build.db", "build/XCBuildData/build.db-wal"):
            self.assertTrue(native.generated(path), path)
        for path in (str(PROJECT), str(PLIST), str(LOCALIZED), "build/XCBuildData-evil/file",
                     "build/XCBuildData", f"{BUNDLE}/Contents/MacOS/{PRODUCT}-evil",
                     f"{BUNDLE}/Contents/_CodeSignature-evil/file",
                     f"{BUNDLE}/Contents/Resources/manifest.json"):
            self.assertFalse(native.generated(path), path)


GIT_WRAPPER = r'''
import json, os, pathlib, subprocess, sys
real = os.environ["SAFETY_REAL_GIT"]
state_path = pathlib.Path(os.environ["SAFETY_GIT_STATE"])
state = json.loads(state_path.read_text())
args = sys.argv[1:]
state["calls"].append(args)
is_push = "push" in args
if is_push:
    state["pushes"] = state.get("pushes", 0) + 1
    mode = state.get("race")
    bare, ref = state["bare"], state["ref"]
    new = args[-1].split(":")[0]
    def git(*arguments):
        return subprocess.check_output([real, "--git-dir=" + bare, *arguments],
                                       text=True).strip()
    if mode == "same-result":
        git("fetch", "--no-tags", str(pathlib.Path.cwd()), new)
        git("update-ref", ref, new)
    elif mode in ("advance", "rewind"):
        git("update-ref", ref, state["race_sha"])
    elif mode == "delete":
        git("update-ref", "-d", ref)
    if mode == "postadvertisement":
        hook = pathlib.Path(bare) / "hooks/pre-receive"
        hook.parent.mkdir(exist_ok=True)
        hook.write_text("#!" + sys.executable + "\nimport os, subprocess\n"
                        "env = {k: v for k, v in os.environ.items() if k not in "
                        "('GIT_QUARANTINE_PATH', 'GIT_OBJECT_DIRECTORY', "
                        "'GIT_ALTERNATE_OBJECT_DIRECTORIES')}\n"
                        "subprocess.check_call(" +
                        repr([real, "--git-dir=" + bare, "update-ref", ref,
                              state["race_sha"]]) + ", env=env)\n")
        hook.chmod(0o755)
if "ls-remote" in args:
    state["reads"] = state.get("reads", 0) + 1
    if state.get("remove_hook_at") == state["reads"]:
        pathlib.Path(state["hook"]).unlink()
    if state.get("mutate_hook_at") == state["reads"]:
        pathlib.Path(state["hook"]).write_text("#!/bin/sh\nexit 0\n")
state_path.write_text(json.dumps(state))
os.execv(real, [real, *args])
'''


FAKE_GH = r'''
import json, os, pathlib, subprocess, sys
from urllib.parse import unquote
path = pathlib.Path(os.environ["SAFETY_GH_STATE"])
state = json.loads(path.read_text())
args = sys.argv[1:]
assert args[:2] == ["api", "--method"], args
method, endpoint = args[2:4]
assert args[4:8] == ["-H", "Accept: application/vnd.github+json",
                     "-H", "X-GitHub-Api-Version: 2022-11-28"], args
assert method in ("GET", "POST"), "mutation/retry/delete forbidden"
body = None
asset = None
if "--input" in args:
    value = args[args.index("--input") + 1]
    if value == "-":
        body = json.loads(sys.stdin.read())
    else:
        assert "-H" in args and "Content-Type: application/octet-stream" in args
        asset = pathlib.Path(value)
        assert asset.is_file()
elif method == "POST":
    raise AssertionError("POST requires input")
call = {"method": method, "endpoint": endpoint, "body": body,
        "asset": None if asset is None else str(asset)}
state["calls"].append(call)
key = method + " " + endpoint
override = state.get("overrides", {}).get(key)
def save():
    path.write_text(json.dumps(state))
if override is not None:
    save()
    if "exit" in override:
        print(override.get("stderr", "synthetic transport failure"), file=sys.stderr)
        sys.exit(override["exit"])
    print(override.get("raw", json.dumps(override.get("json"))))
    sys.exit(0)
base = "repos/miyako/4d-plugin-finder-control/"
tag, sha = state["tag"], state["sha"]
ref = {"ref": "refs/tags/" + tag, "object": {"sha": sha, "type": "commit"}}
if method == "GET" and endpoint.startswith(base + "releases?per_page=100&page="):
    page = int(endpoint.rsplit("=", 1)[1])
    assert 1 <= page <= 4, "pagination must terminate at an empty page"
    result = state.get("pages", [[{"id": 41, "tag_name": "v0.0.1",
                                  "draft": False, "prerelease": False}], []])[page - 1]
elif method == "GET" and endpoint == base + "git/matching-refs/tags/" + tag:
    result = state.get("refs", [])
elif method == "POST" and endpoint == base + "git/refs":
    assert body == {"ref": "refs/tags/" + tag, "sha": sha}, body
    assert not state.get("created_tag"), "must not retry tag creation"
    if not state.get("omit_tag_ref"):
        subprocess.check_call([os.environ["SAFETY_REAL_GIT"], "--git-dir=" + state["bare"],
                               "update-ref", "refs/tags/" + tag, sha, "0" * 40])
    state["created_tag"] = True
    result = ref
elif method == "GET" and endpoint == base + "git/ref/tags/" + tag:
    assert state.get("created_tag")
    result = ref
elif method == "POST" and endpoint == base + "releases":
    assert state.get("created_tag") and not state.get("created_release")
    assert body == {"tag_name": tag, "name": tag, "target_commitish": sha,
                    "draft": False, "prerelease": False,
                    "body": "", "generate_release_notes": False}, body
    state["created_release"] = True
    result = {**body, "id": 1001,
              "upload_url": "https://uploads.github.com/" + base +
                            "releases/1001/assets{?name,label}"}
elif method == "POST" and endpoint.startswith("https://uploads.github.com/" + base +
                                              "releases/1001/assets?name="):
    assert state.get("created_release") and asset is not None
    requested = unquote(endpoint.split("?name=", 1)[1])
    assert requested == asset.name
    uploads = state.setdefault("uploads", [])
    assert requested not in uploads, "must not retry uploads"
    uploads.append(requested)
    result = {"id": 2000 + len(uploads), "name": requested.replace(" ", "."),
              "state": "uploaded", "size": asset.stat().st_size}
else:
    raise AssertionError((method, endpoint, args))
save()
if key in state.get("post_patches", {}):
    result.update(state["post_patches"][key])
override = state.get("post_overrides", {}).get(key)
print(override.get("raw", json.dumps(override.get("json"))) if override else json.dumps(result))
'''


class RealGitFixture(Fixture):
    def setUp(self):
        super().setUp()
        self.bin = self.scratch / "bin"
        self.bin.mkdir()
        self.git_state = self.scratch / "git.json"
        self.gh_state = self.scratch / "gh.json"
        self.bare = self.scratch / "origin.git"
        self.ref = "refs/heads/selected"
        self.env = {
            "PATH": str(self.bin), "HOME": str(self.scratch),
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_ALLOW_PROTOCOL": "file", "GIT_TERMINAL_PROMPT": "0",
            "SAFETY_REAL_GIT": REAL_GIT, "SAFETY_GIT_STATE": str(self.git_state),
            "SAFETY_GH_STATE": str(self.gh_state),
            "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1",
        }
        for name, executable in (("python3", sys.executable), ("dirname", "/usr/bin/dirname")):
            (self.bin / name).symlink_to(executable)
        (self.bin / "git-upload-pack").symlink_to(GIT_EXEC / "git-upload-pack")
        # A local transport inherits the client's core.hooksPath; keep server hooks separate.
        self.executable(self.bin / "git-receive-pack", """
import os, sys
real = os.environ["SAFETY_REAL_GIT"]
os.execv(real, [real, "-c", "core.hooksPath=" + sys.argv[1] + "/hooks",
               "receive-pack", *sys.argv[1:]])
""")
        self.executable(self.bin / "git", GIT_WRAPPER)
        self.executable(self.bin / "gh", FAKE_GH)
        self.git_state.write_text(json.dumps({"calls": [], "bare": str(self.bare), "ref": self.ref}))
        for name in ("bump.py", "release.py", "repository.py", "source_version.py", "native.py"):
            self.write(Path(".github/scripts") / name, (SCRIPTS / name).read_bytes())
        self.hook = self.write(".github/hooks/pre-push", (ROOT / ".github/hooks/pre-push").read_bytes())
        self.hook.chmod(0o755)
        self.write(".gitignore", b"build/*\nignored/*\n")
        self.write("config.txt", b"selected source config\n")
        self.built()
        self.git("init", "--quiet")
        self.git("add", ".")
        self.commit("fixture root")
        self.parent_sha = self.git("rev-parse", "HEAD")
        self.commit("selected fixture", "--allow-empty")
        self.sha = self.git("rev-parse", "HEAD")
        self.git("init", "--bare", "--quiet", str(self.bare))
        self.git("remote", "add", "origin", str(self.bare))
        self.git("push", "--quiet", "--no-follow-tags", "origin", f"HEAD:{self.ref}")
        self.git("checkout", "--quiet", "--detach", self.sha)
        self.update_git_state(calls=[], pushes=0, reads=0, hook=str(self.hook))
        self.reset_gh()

    def executable(self, path, body):
        path.write_text("#!" + sys.executable + "\n" + body)
        path.chmod(0o755)

    def git(self, *args, input=None, check=True):
        result = subprocess.run([REAL_GIT, *args], cwd=self.root, env=self.env,
                                input=input, text=True, capture_output=True)
        if check:
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.strip()
        return result

    def bare_git(self, *args, **kwargs):
        # --git-dir is required even on hosts configured with safe.bareRepository=explicit.
        return self.git("--git-dir=" + str(self.bare), *args, **kwargs)

    def commit(self, message, *extra):
        return self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "commit", "--quiet", *extra, "-m", message)

    def set_fsmonitor_valid(self, path="config.txt"):
        hook = self.scratch / "synthetic-fsmonitor"
        self.executable(hook, "import sys\nsys.stdout.buffer.write(b'fixture-token\\0')\n")
        self.git("config", "core.fsmonitor", str(hook))
        self.git("config", "core.fsmonitorHookVersion", "2")
        self.git("update-index", "--fsmonitor-valid", path)
        self.assertEqual(self.git("ls-files", "-v", "--", path), "H " + path)
        self.assertEqual(self.git("ls-files", "-f", "--", path), "h " + path)

    def state(self):
        return json.loads(self.git_state.read_text())

    def update_git_state(self, **values):
        state = self.state()
        state.update(values)
        self.git_state.write_text(json.dumps(state))

    def reset_gh(self, **values):
        self.gh_state.write_text(json.dumps({
            "calls": [], "bare": str(self.bare), "sha": self.sha,
            "tag": "v" + self.version, **values,
        }))

    def gh(self):
        return json.loads(self.gh_state.read_text())

    def cli(self, helper, *arguments, success=True, **extra):
        result = subprocess.run([sys.executable, str(self.root / ".github/scripts" / helper),
                                 *map(str, arguments)], cwd=self.root,
                                env={**self.env, **extra}, capture_output=True, text=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def bump_cli(self, success=True, **extra):
        return self.cli("bump.py", "patch", "--sha", self.sha, "--ref", self.ref,
                        success=success, **extra)

    def guard_cli(self, old=None, success=False):
        new = self.git("rev-parse", "HEAD")
        old = self.sha if old is None else old
        result = subprocess.run(
            [sys.executable, ".github/scripts/bump.py", "--guard"],
            input=f"{new} {new} {self.ref} {old}\n", text=True, capture_output=True,
            cwd=self.root, env={**self.env, "BUMP_EXPECTED_SHA": old,
                                "BUMP_EXPECTED_REF": self.ref, "BUMP_NEW_SHA": new})
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def publish_cli(self, command="publish", success=True, assets=None, **extra):
        environment = {
            "GH_TOKEN": "synthetic-offline-token", "GITHUB_REPOSITORY": REPO,
            "GITHUB_SHA": self.sha, "GITHUB_OUTPUT": str(self.scratch / "output"),
            **extra,
        }
        arguments = [command, "--sha", self.sha]
        if command == "publish":
            arguments += assets if assets is not None else release.asset_names(self.version)
        return self.cli("release.py", *arguments, success=success, **environment)

    def prepare_release(self):
        self.publish_cli("preflight")
        self.reset_gh()
        self.built(plistlib.FMT_BINARY, plistlib.FMT_BINARY)
        self.write(BUNDLE / f"Contents/MacOS/{PRODUCT}", b"fresh generated executable\0\xff")
        self.write(BUNDLE / "Contents/_CodeSignature/CodeResources", b"signed bytes\0")
        self.write("build/XCBuildData/build.db", b"database\0\xff")
        self.write("build/XCBuildData/build.db-wal", b"wal\0\xff")
        for name in release.asset_names(self.version):
            self.write(name, ("asset " + name).encode())

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob("*")
                if path.is_file() and ".git" not in path.relative_to(self.root).parts}

    def assert_no_mutations(self):
        self.assertFalse(any(call["method"] != "GET" for call in self.gh()["calls"]))
        self.assertEqual(self.bare_git("tag", "--list"), "")

    def assert_before_api(self):
        self.assertEqual(self.gh()["calls"], [])
        self.assertEqual(self.bare_git("tag", "--list"), "")

    def race_commit(self):
        tree = self.bare_git("rev-parse", self.sha + "^{tree}")
        return self.bare_git("-c", "user.name=Race", "-c", "user.email=race@example.invalid",
                             "commit-tree", tree, "-p", self.sha, input="concurrent commit\n")


class BumpIntegrationTests(RealGitFixture):
    def test_detached_no_identity_bot_direct_child_exact_source_diff_and_no_tags(self):
        self.assertNotEqual(self.git("symbolic-ref", "-q", "HEAD", check=False).returncode, 0)
        self.assertNotEqual(self.git("config", "user.name", check=False).returncode, 0)
        self.git("config", "push.followTags", "true")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "tag", "-a", "reachable-annotated", "-m", "must remain local")
        tags = self.git("show-ref", "--tags")
        self.bump_cli()
        new = self.git("rev-parse", "HEAD")
        self.assertEqual(self.git("rev-list", "--parents", "-n", "1", new), f"{new} {self.sha}")
        changed = set(self.git("diff-tree", "--no-commit-id", "--name-only", "-r", new).splitlines())
        self.assertTrue(changed)
        expected = {str(path) for path in SOURCE_PATHS
                    if self.original[path] != (self.root / path).read_bytes()}
        self.assertEqual(changed, expected)
        self.assertTrue(changed.issubset(set(map(str, SOURCE_PATHS))))
        self.assertEqual(self.git("log", "-1", "--format=%an%n%ae%n%cn%n%ce").splitlines(),
                         ["github-actions[bot]", "github-actions[bot]@users.noreply.github.com"] * 2)
        # Literal independent oracle: do not compare only with bump.TRAILER.
        self.assertTrue(self.git("log", "-1", "--format=%B").endswith(
            "Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"))
        self.assertEqual(self.bare_git("rev-parse", self.ref), new)
        self.assertEqual(self.bare_git("tag", "--list"), "")
        self.assertEqual(self.git("show-ref", "--tags"), tags)
        self.assertEqual(self.state()["pushes"], 1)
        pushes = [call for call in self.state()["calls"] if "push" in call]
        index = self.state()["calls"].index(pushes[0])
        self.assertEqual(sum("ls-remote" in call for call in self.state()["calls"][:index]), 2)
        self.assertIn("--no-follow-tags", pushes[0])
        self.assertIn("push.followTags=false", pushes[0])
        self.assertFalse(any(arg.startswith("--force") or arg.startswith("+")
                             for arg in pushes[0]))

    def test_follow_tags_negative_control_really_would_publish_reachable_tag(self):
        self.git("config", "push.followTags", "true")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "tag", "-a", "negative-control", "-m", "reachable")
        self.git("push", "--quiet", "origin", f"HEAD:{self.ref}")
        self.assertEqual(self.bare_git("tag", "--list"), "negative-control")

    def test_hostile_identity_environment_cannot_override_actions_bot(self):
        self.bump_cli(
            GIT_AUTHOR_NAME="Unexpected Author", GIT_AUTHOR_EMAIL="author@example.invalid",
            GIT_COMMITTER_NAME="Unexpected Committer", GIT_COMMITTER_EMAIL="committer@example.invalid")
        bot = "github-actions[bot] <github-actions[bot]@users.noreply.github.com>"
        self.assertEqual(self.git("log", "-1", "--format=%an <%ae>%n%cn <%ce>"), f"{bot}\n{bot}")
        self.assertEqual(self.bare_git("rev-parse", self.ref), self.git("rev-parse", "HEAD"))

    def test_advance_between_final_remote_read_and_push_advertisement(self):
        race = self.race_commit()
        self.update_git_state(race="advance", race_sha=race)
        self.bump_cli(success=False)
        self.assertEqual(self.bare_git("rev-parse", self.ref), race)
        self.assertEqual(self.state()["pushes"], 1)

    def test_rewind_between_final_remote_read_and_push_advertisement(self):
        self.update_git_state(race="rewind", race_sha=self.parent_sha)
        self.bump_cli(success=False)
        self.assertEqual(self.bare_git("rev-parse", self.ref), self.parent_sha)
        self.assertEqual(self.state()["pushes"], 1)

    def test_delete_between_final_remote_read_and_push_advertisement(self):
        self.update_git_state(race="delete")
        self.bump_cli(success=False)
        self.assertNotEqual(self.bare_git("show-ref", "--verify", self.ref,
                                         check=False).returncode, 0)
        self.assertEqual(self.state()["pushes"], 1)

    def test_same_result_between_final_remote_read_and_push_advertisement_is_not_success(self):
        self.update_git_state(race="same-result")
        self.bump_cli(success=False)
        self.assertEqual(self.bare_git("rev-parse", self.ref), self.git("rev-parse", "HEAD"))
        self.assertEqual(self.state()["pushes"], 1)

    def test_postadvertisement_pre_receive_update_preserved_by_nonforce_push(self):
        race = self.race_commit()
        self.update_git_state(race="postadvertisement", race_sha=race)
        result = self.bump_cli(success=False)
        self.assertEqual(self.bare_git("rev-parse", self.ref), race, result.stderr)
        self.assertEqual(self.state()["pushes"], 1)

    def test_missing_hook_rejected_before_commit_or_push(self):
        self.hook.unlink()
        self.bump_cli(success=False)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.sha)
        self.assertEqual(self.state()["pushes"], 0)

    def test_nonexecutable_hook_rejected_before_commit_or_push(self):
        self.hook.chmod(0o644)
        self.bump_cli(success=False)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.sha)
        self.assertEqual(self.state()["pushes"], 0)

    def test_executable_hook_must_match_exact_head_blob_before_edits(self):
        self.hook.write_text("#!/bin/sh\nexit 0\n")
        before = {path: (self.root / path).read_bytes() for path in SOURCE_PATHS}
        result = self.bump_cli(success=False)
        self.assertIn("committed executable blob", result.stderr)
        self.assertEqual(before, {path: (self.root / path).read_bytes() for path in SOURCE_PATHS})
        self.assertEqual(self.git("rev-parse", "HEAD"), self.sha)
        self.assertEqual(self.state()["pushes"], 0)

    def test_symlink_hook_rejected_before_edits(self):
        target = self.scratch / "hook-target"
        target.write_bytes(self.hook.read_bytes())
        target.chmod(0o755)
        self.hook.unlink()
        self.hook.symlink_to(target)
        before = {path: (self.root / path).read_bytes() for path in SOURCE_PATHS}
        self.bump_cli(success=False)
        self.assertEqual(before, {path: (self.root / path).read_bytes() for path in SOURCE_PATHS})
        self.assertEqual(self.git("rev-parse", "HEAD"), self.sha)
        self.assertEqual(self.state()["pushes"], 0)

    def test_hook_rechecked_after_final_remote_read(self):
        self.update_git_state(remove_hook_at=2)
        self.bump_cli(success=False)
        self.assertNotEqual(self.git("rev-parse", "HEAD"), self.sha)
        self.assertEqual(self.state()["pushes"], 0)
        self.assertEqual(self.bare_git("rev-parse", self.ref), self.sha)

    def test_executable_hook_content_rechecked_after_final_remote_read(self):
        self.update_git_state(mutate_hook_at=2)
        result = self.bump_cli(success=False)
        self.assertIn("committed executable blob", result.stderr)
        self.assertNotEqual(self.git("rev-parse", "HEAD"), self.sha)
        self.assertEqual(self.state()["pushes"], 0)
        self.assertEqual(self.bare_git("rev-parse", self.ref), self.sha)

    def test_pristine_hidden_index_flags_forbid_bump_before_edits(self):
        for flag, undo in (("--assume-unchanged", "--no-assume-unchanged"),
                           ("--skip-worktree", "--no-skip-worktree")):
            with self.subTest(flag=flag):
                self.git("update-index", flag, "config.txt")
                result = self.bump_cli(success=False)
                self.assertIn("index flags", result.stderr)
                self.assertEqual(self.git("rev-parse", "HEAD"), self.sha)
                self.assertEqual(self.state()["pushes"], 0)
                self.git("update-index", undo, "config.txt")

    def test_fsmonitor_valid_flag_forbids_bump_before_edits(self):
        self.set_fsmonitor_valid()
        before = {path: (self.root / path).read_bytes() for path in SOURCE_PATHS}
        result = self.bump_cli(success=False)
        self.assertIn("index flags", result.stderr)
        self.assertEqual(before, {path: (self.root / path).read_bytes() for path in SOURCE_PATHS})
        self.assertEqual(self.git("rev-parse", "HEAD"), self.sha)
        self.assertEqual(self.state()["pushes"], 0)

    def test_guard_rejects_multiple_updates_wrong_sha_and_local_ref(self):
        self.bump_cli()
        new = self.git("rev-parse", "HEAD")
        env = {"BUMP_EXPECTED_SHA": self.sha, "BUMP_EXPECTED_REF": self.ref, "BUMP_NEW_SHA": new}
        good = f"{new} {new} {self.ref} {self.sha}\n"
        for row in (good + good, good.replace(self.sha, "0" * 40),
                    good.replace(self.ref, "refs/heads/other"),
                    good.replace(new + " ", "refs/heads/local ", 1), ""):
            with self.subTest(row=row):
                result = subprocess.run([sys.executable, ".github/scripts/bump.py", "--guard"],
                                        input=row, text=True, capture_output=True,
                                        cwd=self.root, env={**self.env, **env})
                self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_guard_rejects_empty_direct_child_even_with_literal_trailer(self):
        self.commit("empty\n\n" + TRAILER, "--allow-empty")
        self.guard_cli()

    def test_guard_rejects_non_source_diff_even_with_literal_trailer(self):
        self.write("config.txt", b"unrelated edit\n")
        self.git("add", "config.txt")
        self.commit("unexpected config\n\n" + TRAILER)
        self.guard_cli()

    def test_guard_rejects_non_direct_child(self):
        source_version.bump("patch", self.root)
        self.git("add", *map(str, SOURCE_PATHS))
        self.commit("bump\n\n" + TRAILER)
        self.guard_cli(old=self.parent_sha)

    def test_guard_requires_literal_coauthor_at_message_end(self):
        source_version.bump("patch", self.root)
        self.git("add", *map(str, SOURCE_PATHS))
        self.commit("bump\n\n" + TRAILER + "\n\nnot at the end")
        self.guard_cli()


class PublicationIntegrationTests(RealGitFixture):
    def test_real_cli_publication_preserves_generated_tracked_and_ignored_bytes(self):
        self.prepare_release()
        self.assertNotEqual(self.git("diff", "--name-only"), "")
        self.assertNotEqual(self.git("check-ignore", "build/XCBuildData/build.db"), "")
        before = self.snapshot()
        self.publish_cli()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.sha)
        self.assertEqual(self.bare_git("rev-parse", "refs/tags/v" + self.version), self.sha)
        calls = self.gh()["calls"]
        self.assertEqual([call["method"] for call in calls],
                         ["GET", "GET", "GET", "POST", "GET", "POST", "POST", "POST"])
        self.assertEqual([call["body"] for call in calls if call["endpoint"].endswith("/releases")],
                         [{"tag_name": "v" + self.version, "name": "v" + self.version,
                           "target_commitish": self.sha, "draft": False, "prerelease": False,
                           "body": "", "generate_release_notes": False}])
        self.assertEqual(self.gh()["uploads"], release.asset_names(self.version))

    def test_short_release_page_still_requires_a_terminating_empty_page(self):
        self.publish_cli("preflight")
        endpoints = [call["endpoint"] for call in self.gh()["calls"]]
        self.assertIn(f"repos/{REPO}/releases?per_page=100&page=2", endpoints)

    def test_initial_ignored_database_is_not_allowed(self):
        self.write("build/XCBuildData/build.db", b"premature database")
        self.publish_cli("preflight", success=False)
        self.assert_before_api()

    def test_pristine_assume_unchanged_flag_forbids_preflight(self):
        self.git("update-index", "--assume-unchanged", "config.txt")
        result = self.publish_cli("preflight", success=False)
        self.assertIn("index flags", result.stderr)
        self.assert_before_api()

    def test_pristine_skip_worktree_flag_forbids_preflight(self):
        self.git("update-index", "--skip-worktree", "config.txt")
        result = self.publish_cli("preflight", success=False)
        self.assertIn("index flags", result.stderr)
        self.assert_before_api()

    def test_fsmonitor_valid_flag_forbids_preflight(self):
        self.set_fsmonitor_valid()
        result = self.publish_cli("preflight", success=False)
        self.assertIn("index flags", result.stderr)
        self.assert_before_api()

    def test_fsmonitor_valid_generated_path_forbids_final_publication(self):
        self.prepare_release()
        self.set_fsmonitor_valid(str(BUNDLE / f"Contents/MacOS/{PRODUCT}"))
        result = self.publish_cli(success=False)
        self.assertIn("index flags", result.stderr)
        self.assert_before_api()

    def test_hidden_flags_on_allowlisted_generated_paths_forbid_final_publication(self):
        self.prepare_release()
        path = str(BUNDLE / f"Contents/MacOS/{PRODUCT}")
        for flag, undo in (("--assume-unchanged", "--no-assume-unchanged"),
                           ("--skip-worktree", "--no-skip-worktree")):
            with self.subTest(flag=flag):
                self.git("update-index", flag, path)
                result = self.publish_cli(success=False)
                self.assertIn("index flags", result.stderr)
                self.assert_before_api()
                self.git("update-index", undo, path)

    def test_final_source_drift_fails_before_api(self):
        self.prepare_release()
        self.replace(LOCALIZED, "Copyright 2021", "Copyright 2022")
        self.publish_cli(success=False)
        self.assert_before_api()

    def test_final_raw_config_drift_fails_before_api(self):
        self.prepare_release()
        self.write("config.txt", b"dirty tracked configuration")
        self.publish_cli(success=False)
        self.assert_before_api()

    def test_final_index_drift_fails_before_api(self):
        self.prepare_release()
        self.write("config.txt", b"staged configuration")
        self.git("add", "config.txt")
        self.publish_cli(success=False)
        self.assert_before_api()

    def test_reversed_staged_config_is_detected_even_when_worktree_matches_head(self):
        self.prepare_release()
        self.write("config.txt", b"staged configuration")
        self.git("add", "config.txt")
        self.write("config.txt", b"selected source config\n")
        self.publish_cli(success=False)
        self.assert_before_api()

    def test_assume_unchanged_does_not_hide_raw_drift(self):
        self.prepare_release()
        self.git("update-index", "--assume-unchanged", "config.txt")
        self.write("config.txt", b"hidden raw drift")
        self.assertEqual(self.git("diff", "--", "config.txt"), "")
        self.publish_cli(success=False)
        self.assert_before_api()

    def test_skip_worktree_does_not_hide_raw_drift(self):
        self.prepare_release()
        self.git("update-index", "--skip-worktree", "config.txt")
        self.write("config.txt", b"hidden raw drift")
        self.assertEqual(self.git("diff", "--", "config.txt"), "")
        self.publish_cli(success=False)
        self.assert_before_api()

    def test_final_head_drift_fails_before_api(self):
        self.prepare_release()
        self.commit("unexpected HEAD", "--allow-empty")
        self.publish_cli(success=False)
        self.assert_before_api()

    def test_final_ignored_source_fails_before_api(self):
        self.prepare_release()
        self.write("ignored/source.cpp", b"unexpected ignored source")
        self.publish_cli(success=False)
        self.assert_before_api()

    def test_final_ignored_generated_prefix_sibling_fails_before_api(self):
        self.prepare_release()
        self.write("build/XCBuildData-evil/source.cpp", b"not generated")
        self.publish_cli(success=False)
        self.assert_before_api()

    def test_final_untracked_source_fails_before_api(self):
        self.prepare_release()
        self.write("unexpected.cpp", b"unexpected source")
        self.publish_cli(success=False)
        self.assert_before_api()

    def test_final_tracked_file_mode_drift_fails_before_api(self):
        self.prepare_release()
        (self.root / "config.txt").chmod(0o755)
        self.publish_cli(success=False)
        self.assert_before_api()

    def test_final_tracked_symlink_drift_fails_before_api(self):
        self.prepare_release()
        path = self.root / "config.txt"
        path.unlink()
        path.symlink_to(self.root / PLIST)
        self.publish_cli(success=False)
        self.assert_before_api()

    def test_wrong_repository_sha_or_missing_token_fails_before_api(self):
        for environment in ({"GITHUB_REPOSITORY": "other/repository"},
                            {"GITHUB_SHA": "0" * 40}, {"GH_TOKEN": "", "GITHUB_TOKEN": ""}):
            with self.subTest(environment=environment):
                self.publish_cli("preflight", success=False, **environment)
                self.assert_before_api()

    def test_github_token_alone_is_not_explicit_gh_token(self):
        self.publish_cli("preflight", success=False, GH_TOKEN="",
                         GITHUB_TOKEN="synthetic-wrong-token-kind")
        self.assert_before_api()

    def test_asset_order_paths_empty_and_symlinks_fail_before_api(self):
        self.prepare_release()
        names = release.asset_names(self.version)
        for assets in (names[::-1], ["./" + name for name in names], names[:1]):
            with self.subTest(assets=assets):
                self.publish_cli(success=False, assets=assets)
                self.assert_before_api()
        self.write(names[0], b"")
        self.publish_cli(success=False)
        self.assert_before_api()
        path = self.root / names[0]
        path.unlink()
        path.symlink_to(self.root / names[1])
        self.publish_cli(success=False)
        self.assert_before_api()

    def test_existing_draft_on_later_page_forbids_mutation(self):
        self.prepare_release()
        other = {"id": 40, "tag_name": "v0.0.0", "draft": False, "prerelease": False}
        draft = {"id": 42, "tag_name": "v" + self.version, "draft": True, "prerelease": False}
        self.reset_gh(pages=[[other], [draft], []])
        self.publish_cli(success=False)
        self.assert_no_mutations()
        self.assertEqual(len([call for call in self.gh()["calls"]
                              if "/releases?" in call["endpoint"]]), 3)

    def test_api_existing_tag_same_sha_is_never_reused(self):
        self.prepare_release()
        self.reset_gh(refs=[{"ref": "refs/tags/v" + self.version,
                             "object": {"sha": self.sha, "type": "commit"}}])
        self.publish_cli(success=False)
        self.assert_no_mutations()

    def test_lsremote_existing_tag_same_sha_is_never_reused(self):
        self.prepare_release()
        self.bare_git("update-ref", "refs/tags/v" + self.version, self.sha)
        self.publish_cli(success=False)
        self.assertFalse(any(call["method"] != "GET" for call in self.gh()["calls"]))
        self.assertEqual(self.bare_git("rev-parse", "refs/tags/v" + self.version), self.sha)

    def test_matching_tag_prefix_is_not_exact_tag_occupancy(self):
        self.prepare_release()
        self.reset_gh(refs=[{"ref": "refs/tags/v" + self.version + "-other",
                             "object": {"sha": self.sha, "type": "tag"}}])
        self.publish_cli()

    def test_malformed_json_duplicate_and_nonfinite_fail_closed(self):
        endpoint = f"GET repos/{REPO}/releases?per_page=100&page=1"
        for raw in ("not json", '{"id":1,"id":2}', "[NaN]", "[Infinity]", "[-Infinity]"):
            with self.subTest(raw=raw):
                self.reset_gh(overrides={endpoint: {"raw": raw}})
                self.publish_cli("preflight", success=False)
                self.assert_no_mutations()

    def test_release_page_schema_and_duplicate_ids_fail_closed(self):
        entry = {"id": 1, "tag_name": "v0.0.1", "draft": False, "prerelease": False}
        for pages in (
            [[entry], [entry], []],
            [[{**entry, "id": True}]],
            [[{**entry, "id": 0}]],
            [[{**entry, "draft": 0}]],
            [[{**entry, "prerelease": "false"}]],
            [[{**entry, "tag_name": ""}]],
            [[{}]], [None], [[entry] * 101],
        ):
            with self.subTest(pages=pages):
                self.reset_gh(pages=pages)
                self.publish_cli("preflight", success=False)
                self.assert_no_mutations()

    def test_later_release_page_404_auth_network_and_schema_fail_closed(self):
        endpoint = f"GET repos/{REPO}/releases?per_page=100&page=2"
        for override in (
            {"exit": 1, "stderr": "HTTP 404"},
            {"exit": 1, "stderr": "HTTP 401 unauthorized"},
            {"exit": 1, "stderr": "network unavailable"},
            {"raw": "{"}, {"json": {"message": "unexpected object"}},
        ):
            with self.subTest(override=override):
                self.reset_gh(overrides={endpoint: override})
                self.publish_cli("preflight", success=False)
                self.assert_no_mutations()
                self.assertEqual(len(self.gh()["calls"]), 2)

    def test_matching_refs_malformed_duplicate_and_transport_fail_closed(self):
        endpoint = f"GET repos/{REPO}/git/matching-refs/tags/v{self.version}"
        good = {"ref": "refs/tags/v" + self.version + "-other",
                "object": {"sha": self.sha, "type": "commit"}}
        for override in (
            {"json": {}}, {"json": [good, good]},
            {"json": [{"ref": "refs/heads/wrong", "object": good["object"]}]},
            {"json": [{**good, "object": {"sha": "bad", "type": "commit"}}]},
            {"json": [{**good, "object": {"sha": self.sha, "type": "tree"}}]},
            {"exit": 1, "stderr": "HTTP 404"},
        ):
            with self.subTest(override=override):
                self.reset_gh(overrides={endpoint: override})
                self.publish_cli("preflight", success=False)
                self.assert_no_mutations()

    def test_tag_creation_failure_stops_without_retry_rollback_or_release(self):
        self.prepare_release()
        endpoint = f"POST repos/{REPO}/git/refs"
        self.reset_gh(overrides={endpoint: {"exit": 1, "stderr": "HTTP 422 conflict"}})
        result = self.publish_cli(success=False)
        self.assertIn("Manual recovery", result.stderr)
        self.assertIn("creation may have succeeded", result.stderr)
        self.assertEqual([call["method"] for call in self.gh()["calls"]].count("POST"), 1)

    def test_created_tag_verification_failure_retains_tag_without_release(self):
        self.prepare_release()
        endpoint = f"GET repos/{REPO}/git/ref/tags/v{self.version}"
        self.reset_gh(overrides={endpoint: {"json": {
            "ref": "refs/tags/v" + self.version,
            "object": {"sha": "0" * 40, "type": "commit"}}}})
        result = self.publish_cli(success=False)
        self.assertIn(f"tag v{self.version} retained", result.stderr)
        self.assertEqual(self.bare_git("rev-parse", "refs/tags/v" + self.version), self.sha)
        self.assertFalse(self.gh().get("created_release"))
        self.assertEqual([call["method"] for call in self.gh()["calls"]].count("POST"), 1)

    def test_api_tag_agreement_without_real_remote_tag_fails_verification(self):
        self.prepare_release()
        self.reset_gh(omit_tag_ref=True)
        result = self.publish_cli(success=False)
        self.assertIn("Remote advertisement failed", result.stderr)
        self.assertIn("retained", result.stderr)
        self.assertEqual(self.bare_git("tag", "--list"), "")
        self.assertFalse(self.gh().get("created_release"))

    def test_malformed_tag_creation_response_retains_actual_tag(self):
        self.prepare_release()
        endpoint = f"POST repos/{REPO}/git/refs"
        self.reset_gh(post_patches={endpoint: {"object": {"sha": "0" * 40, "type": "commit"}}})
        result = self.publish_cli(success=False)
        self.assertIn("creation may have succeeded", result.stderr)
        self.assertEqual(self.bare_git("rev-parse", "refs/tags/v" + self.version), self.sha)
        self.assertFalse(self.gh().get("created_release"))

    def test_release_failure_retains_real_tag_and_never_retries(self):
        self.prepare_release()
        self.reset_gh(overrides={f"POST repos/{REPO}/releases":
                                {"exit": 1, "stderr": "network after tag"}})
        result = self.publish_cli(success=False)
        self.assertIn("release creation may have succeeded; ID unknown", result.stderr)
        self.assertEqual(self.bare_git("rev-parse", "refs/tags/v" + self.version), self.sha)
        self.assertEqual([call["method"] for call in self.gh()["calls"]].count("POST"), 2)

    def test_second_upload_failure_retains_release_and_first_asset(self):
        self.prepare_release()
        from urllib.parse import quote
        name = release.asset_names(self.version)[1]
        endpoint = (f"POST https://uploads.github.com/repos/{REPO}/releases/1001/assets?name="
                    + quote(name, safe=""))
        self.reset_gh(overrides={endpoint: {"exit": 1, "stderr": "upload disconnected"}})
        result = self.publish_cli(success=False)
        self.assertIn("release ID 1001 retained", result.stderr)
        self.assertIn(release.asset_names(self.version)[0], result.stderr)
        self.assertIn(f"upload of {name} may have succeeded", result.stderr)
        self.assertTrue(self.gh()["created_release"])
        self.assertEqual(self.gh()["uploads"], release.asset_names(self.version)[:1])
        self.assertEqual([call["method"] for call in self.gh()["calls"]].count("POST"), 4)

    def reject_response_patch(self, stage, patch):
        self.prepare_release()
        if stage == "release":
            endpoint = f"POST repos/{REPO}/releases"
            expected_posts = 2
        else:
            from urllib.parse import quote
            endpoint = (f"POST https://uploads.github.com/repos/{REPO}/releases/1001/assets?name="
                        + quote(release.asset_names(self.version)[0], safe=""))
            expected_posts = 3
        self.reset_gh(post_patches={endpoint: patch})
        before = self.snapshot()
        result = self.publish_cli(success=False)
        self.assertIn("Manual recovery required", result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.bare_git("rev-parse", "refs/tags/v" + self.version), self.sha)
        calls = self.gh()["calls"]
        self.assertEqual(sum(call["method"] == "POST" for call in calls), expected_posts)
        keys = [(call["method"], call["endpoint"]) for call in calls]
        self.assertEqual(len(keys), len(set(keys)), "failed operation must not be retried")
        self.assertTrue(all(call["method"] in ("GET", "POST") for call in calls))


def response_case(stage, patch):
    def test(self):
        self.reject_response_patch(stage, patch)
    return test


for _name, _stage, _patch in (
    ("release_reused_id", "release", {"id": 41}),
    ("release_boolean_id", "release", {"id": True}),
    ("release_nonpositive_id", "release", {"id": 0}),
    ("release_wrong_tag", "release", {"tag_name": "v99.99.99"}),
    ("release_wrong_name", "release", {"name": "unexpected title"}),
    ("release_wrong_target", "release", {"target_commitish": "0" * 40}),
    ("release_draft", "release", {"draft": True}),
    ("release_prerelease", "release", {"prerelease": True}),
    ("release_nonboolean_flag", "release", {"draft": 0}),
    ("release_generated_body", "release", {"body": "generated notes"}),
    ("release_wrong_upload_host", "release", {"upload_url": "https://example.invalid/{?name,label}"}),
    ("upload_wrong_name", "upload", {"name": "wrong.zip"}),
    ("upload_boolean_id", "upload", {"id": True}),
    ("upload_nonpositive_id", "upload", {"id": 0}),
    ("upload_wrong_size", "upload", {"size": 0}),
    ("upload_boolean_size", "upload", {"size": True}),
    ("upload_incomplete_state", "upload", {"state": "new"}),
):
    setattr(PublicationIntegrationTests, "test_rejects_" + _name,
            response_case(_stage, _patch))


if __name__ == "__main__":
    unittest.main()
