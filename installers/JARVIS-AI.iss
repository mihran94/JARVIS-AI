; Unsigned beta installer; no credentials or private user data bundled.
#define AppName "JARVIS AI"
#define AppVersion "0.3.0"
[Setup]
AppId={{C55EB66E-3D4F-47B9-8804-01975A9740E1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=JARVIS AI
DefaultDirName={localappdata}\Programs\JarvisAI
DefaultGroupName=JARVIS AI
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=JarvisAI-Setup-Windows-x64
ArchitecturesAllowed=x64compatible
Compression=lzma
SolidCompression=yes
UninstallDisplayIcon={app}\JarvisAI.exe
WizardStyle=modern

[Files]
Source: "..\dist\JarvisAI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\JARVIS AI"; Filename: "{app}\JarvisAI.exe"
Name: "{autodesktop}\JARVIS AI"; Filename: "{app}\JarvisAI.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; GroupDescription: "Additional options:"; Flags: unchecked

[Run]
Filename: "{app}\JarvisAI.exe"; Description: "Launch JARVIS AI"; Flags: nowait postinstall skipifsilent
