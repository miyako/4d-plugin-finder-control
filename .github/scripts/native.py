"""Classify only this project's proven generated outputs for final publication."""

from pathlib import Path


PRODUCT = "Finder Control"
BUNDLE = Path("test/Plugins") / (PRODUCT + ".bundle")
FILES = tuple(BUNDLE / relative for relative in (
    f"Contents/MacOS/{PRODUCT}",
    "Contents/Info.plist",
    "Contents/Resources/English.lproj/InfoPlist.strings",
))
DIRECTORIES = (
    BUNDLE / "Contents/_CodeSignature",
    Path("build/XCBuildData"),
    Path("build/Finder Control.build"),
    Path("build/Default/Finder Control.build"),
    Path("test/Plugins/Finder Control.build"),
    Path("test/Plugins/Default/Finder Control.build"),
)


def generated(path):
    return (path in set(map(str, FILES))
            or any(path.startswith(str(directory) + "/") for directory in DIRECTORIES))
