; Plate-A-Pixel Windows installer script (Inno Setup).
;
; Prerequisite: build the app first with pyside6-deploy (run from the repo
; root: `pyside6-deploy main.py`). That produces a standalone folder -
; typically `main.dist\` next to main.py, containing main.exe and every
; bundled dependency (PySide6, numpy, scipy, trimesh, manifold3d, ...).
; Check what pyside6-deploy actually named that folder/exe on your machine
; (it's configurable in the pysidedeploy.spec file it generates on first
; run) and adjust SourceExeFolder/SourceExeName below to match - they will
; not necessarily be exactly "main.dist"/"main.exe".
;
; To build the installer: open this file in the Inno Setup Compiler (or
; run `ISCC.exe packaging\installer.iss` from a command prompt) - it
; writes the finished installer to packaging\Output\.
;
; Code signing: sign main.exe (inside SourceExeFolder) with signtool
; BEFORE compiling this script, and sign the installer .exe this script
; produces AFTER compiling it - see the project's own notes on this.

#define MyAppName "Plate-A-Pixel"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Dylan Berndt"
#define MyAppExeName "main.exe"
; Folder pyside6-deploy/Nuitka wrote the standalone build to, relative to
; this .iss file's own location (packaging\) - "..\main.dist" assumes the
; default Nuitka standalone naming convention (<script-name>.dist) with
; main.py at the repo root right above packaging\. Update this if yours
; differs.
#define SourceExeFolder "..\main.dist"

[Setup]
; A fresh, random GUID - generate your own (Tools > Generate GUID in the
; Inno Setup IDE) and keep it forever once you have real users: Windows
; uses this to recognize "this is the same app" across versions for
; upgrades/uninstalls. Do not reuse this placeholder for a real release.
AppId={{B3C1E4A0-3E9F-4C6A-9B0E-6B1E7C6E9B10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
; Per-user install (no admin prompt) is friendlier for a first release;
; switch to "lowest" (system-wide, needs admin) later if you want every
; user on a shared machine to see it without each installing separately.
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename={#MyAppName}-{#MyAppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Uncomment once you have an .ico (see also pysidedeploy.spec's own icon
; field - use the same one for both so the taskbar and the installer
; match):
; SetupIconFile=icon.ico
; UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; Pulls in the entire standalone build folder pyside6-deploy produced -
; main.exe plus every bundled Python/Qt/native dependency next to it.
Source: "{#SourceExeFolder}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
