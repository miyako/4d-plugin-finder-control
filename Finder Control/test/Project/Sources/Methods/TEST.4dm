//%attributes = {}
$file:=Folder:C1567(fk desktop folder:K87:19).file("test")
$file.setText("aaaa")
$path:=$file.platformPath

$success:=Finder trash ($path)

