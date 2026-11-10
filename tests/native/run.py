#!/usr/bin/env python3
"""Unsigned macOS ownership regressions; no Xcode, real Finder, or release tools."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
CASES = (
    "setters-empty-owner", "picture-empty-owner", "getter-owned-results",
    "getter-owning-handoffs", "failed-getter-string", "failed-getter-boolean",
    "failed-getter-number", "failed-getter-object", "failed-getter-collection",
    "stringify-returns", "stringify-raw-zero-sentinel", "array-copy-transfer",
    "array-rejected-destination", "array-allocation-rejection", "scalar-copy-return",
    "stubbed-exported-dispatcher",
)
SDK_SHA256 = "5bac571c5c4cafd280fa7f23d775458a23701287e8735be27d4a2190002f4e3f"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=HERE.parents[1])
    parser.add_argument("--workdir", type=Path, required=True,
                        help="existing dedicated session-artifact directory")
    args = parser.parse_args()
    source = args.source.resolve()
    sdk = source / "4D Plugin API"
    if hashlib.sha256((sdk / "4DPluginAPI.c").read_bytes()).hexdigest() != SDK_SHA256:
        parser.error("unexpected SDK implementation; re-audit its contracts first")
    args.workdir.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="ownership-", dir=args.workdir) as temporary:
        executable = Path(temporary) / "ownership"
        command = [
            "clang++", "-x", "objective-c++", "-std=c++17", "-g",
            "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
            "-Wno-deprecated-declarations", "-Wno-multichar", "-Wno-null-conversion",
            "-I" + str(HERE / "stubs"), "-I" + str(source),
            "-I" + str(sdk), "-I" + str(sdk / "Classes"), "-I" + str(source / "support"),
            str(HERE / "ownership.mm"), str(sdk / "4DPluginAPI.c"),
            str(source / "4DPlugin-Finder-Control.cpp"),
            str(sdk / "Classes/C_TEXT.cpp"), str(sdk / "Classes/C_LONGINT.cpp"),
            str(sdk / "Classes/ARRAY_TEXT.cpp"), str(source / "support/4DPlugin-JSON.cpp"),
            "-framework", "Cocoa", "-o", str(executable),
        ]
        subprocess.run(command, check=True)
        failures = []
        env = {**os.environ, "ASAN_OPTIONS": "detect_leaks=0:halt_on_error=1",
               "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1"}
        for case in CASES:
            for empty in ("allocated", "null"):
                result = subprocess.run([str(executable), case, empty], env=env)
                if result.returncode:
                    failures.append(f"{case}/{empty}")
        if failures:
            raise SystemExit("FAILED: " + ", ".join(failures))
        print(f"PASS {len(CASES) * 2} cases; ASan/UBSan and explicit ownership balances")


if __name__ == "__main__":
    main()
