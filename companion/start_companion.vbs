' Lance le compagnon Deezer en tache de fond, SANS fenetre, de maniere PORTABLE.
' Aucun chemin en dur : detecte automatiquement l'installation Python.
' Placer un raccourci vers ce fichier dans le dossier Demarrage (shell:startup)
' pour un lancement automatique a l'ouverture de session.

Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
pyScript  = scriptDir & "\deezer_companion.py"
tmp       = fso.GetSpecialFolder(2) & "\dz_pyexe.txt"   ' dossier temporaire

' Candidats, resolus via cmd (gere les alias d'execution du Store)
names = Array("python", "python3", "python3.10", "py")

exePath = ""
For Each n In names
    If fso.FileExists(tmp) Then fso.DeleteFile(tmp)
    oneliner = "import sys; open(r'" & tmp & "','w').write(sys.executable)"
    sh.Run "cmd /c " & n & " -c """ & oneliner & """", 0, True   ' cache + attend
    If fso.FileExists(tmp) Then
        exePath = Trim(fso.OpenTextFile(tmp).ReadAll())
        fso.DeleteFile(tmp)
        If exePath <> "" And fso.FileExists(exePath) Then Exit For
        exePath = ""
    End If
Next

If exePath = "" Then
    MsgBox "Python introuvable. Installe Python (python.org ou Microsoft Store) puis reessaie.", 16, "Deezer companion"
    WScript.Quit 1
End If

' Preferer pythonw.exe (aucune console) s'il est present a cote de python.exe
pyw = fso.BuildPath(fso.GetParentFolderName(exePath), "pythonw.exe")
If fso.FileExists(pyw) Then
    runner = pyw
Else
    runner = exePath
End If

sh.Run """" & runner & """ """ & pyScript & """", 0, False
