#define AppName "JARVIS BLUE"
#define AppVersion "0.3.0-dev"
[Setup]
AppId={{E745A7B1-72D4-49A0-A52A-C0DEB96B1792}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\JARVIS BLUE
DefaultGroupName=JARVIS BLUE
OutputDir=..\dist\installer
OutputBaseFilename=JARVIS-BLUE-Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\JARVIS-BLUE.exe
[Files]
Source: "..\dist\JARVIS-BLUE\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\JARVIS BLUE"; Filename: "{app}\JARVIS-BLUE.exe"
Name: "{autodesktop}\JARVIS BLUE"; Filename: "{app}\JARVIS-BLUE.exe"; Tasks: desktopicon
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"
[Run]
Filename: "{app}\JARVIS-BLUE.exe"; Description: "Launch JARVIS BLUE"; Flags: nowait postinstall skipifsilent
