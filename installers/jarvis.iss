; Inno Setup script for JARVIS AI.
;
; It makes a single installer file that puts the program in the user's own
; program folder, adds the shortcuts, writes the uninstall entry and keeps
; the provider keys out of the program folder.
;
; The owner needs Inno Setup 6 on the Windows machine:
;
;     https://jrsoftware.org/isinfo.php
;
; Then, in the repository:
;
;     installers\build.cmd
;     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installers\jarvis.iss
;
; The result is dist\JARVIS-AI-0.3.0-setup.exe.

#define AppName "JARVIS AI"
#define AppVersion "0.3.0"
#define AppPublisher "JARVIS AI"
#define AppExeName "JarvisAI.exe"

[Setup]
AppId={{7C0F2B1E-6E6E-4A9D-9D2E-1F6C0A5B4E21}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\JarvisAI
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=JARVIS-AI-{#AppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; The build is unsigned, so the owner has to accept the unknown publisher.
; Nothing is installed before that question.
DisableDirPage=no
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startmenuicon"; Description: "Create a start menu shortcut"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Files]
Source: "..\dist\JarvisAI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\JarvisAI-RELEASE.txt"; DestDir: "{app}"; DestName: "JarvisAI-RELEASE.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startmenuicon
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  { The program is unsigned. Windows shows a warning. The owner can read
    what it is before accepting it, so the question is not hidden. }
  Result := True;
end;
