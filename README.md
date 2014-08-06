4d-plugin-finder-control
========================

This plugin allows 4D to read and write properties specific to the Finder on OS X, such as comments.
Comments are imported (indexed) by Spotlight, which makes the item easier to find.

Instead of xattr, it uses the Cocoa Scripting Bridge to control the Finder directly.

The advantage is that the comments are not only recognized by mdfind (which is also true for Open Meta), they are also displayed in the "Get Info" panel.

Example
-------

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
