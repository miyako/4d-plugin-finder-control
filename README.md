4d-plugin-finder-control
========================

This plugin allows 4D to read and write properties specific to the Finder on OS X, such as comments.
Comments are imported (indexed) by Spotlight, which makes the item easier to find.

Instead of [xattr](https://developer.apple.com/library/mac/documentation/Darwin/Reference/Manpages/man1/xattr.1.html), it uses the Cocoa [Scripting Bridge] (https://developer.apple.com/library/mac/documentation/Cocoa/Conceptual/ScriptingBridgeConcepts/Introduction/Introduction.html) to control the Finder directly.

The advantage is that the comments are not only recognized by [mdfind](https://developer.apple.com/library/mac/documentation/Darwin/Reference/ManPages/man1/mdfind.1.html) (which is also true for [OpenMeta](https://code.google.com/p/openmeta/)), they are also displayed in the "Get Info" panel.

Not directly linked to Finder, but the plugin also provides an alternative "SORT ARRAY" method, which sorts an array in the same way as Finder. "File 1", "File 11", "File 2" will appear in their numerical order, to give an obvious example.

### Platform

| carbon | cocoa | win32 | win64 |
|:------:|:-----:|:---------:|:---------:|
|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|||

### Version

<img src="https://cloud.githubusercontent.com/assets/1725068/18940649/21945000-8645-11e6-86ed-4a0f800e5a73.png" width="32" height="32" /> <img src="https://cloud.githubusercontent.com/assets/1725068/18940648/2192ddba-8645-11e6-864d-6d5692d55717.png" width="32" height="32" />

### Examples

```
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

//SHOW ON DISK
$success:=Finder reveal ($path)

$temp:=System folder(Desktop)+Generate UUID;
COPY DOCUMENT($path;$temp)

//move to trash
$success:=Finder set locked ($temp;0)
$success:=Finder trash ($temp)

//utility method; sort like Finder
ARRAY TEXT($test;5)

$test{0}:="test 1"
$test{1}:="test 11"
$test{2}:="test 10"
$test{3}:="test 2"
$test{4}:="test 21"
$test{5}:="test 20"

Finder SORT ARRAY ($test)
```
