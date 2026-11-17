; Inno Setup script: turns the PyInstaller build into Trail-Setup.exe
; Built by build.ps1. Installs per-user (no admin prompt).

#define AppVersion "1.0.0"

[Setup]
AppId={{B3F1A0D2-5C7E-4E8A-9A61-7D2C4E9F1B30}
AppName=Trail
AppVersion={#AppVersion}
AppPublisher=Trail
AppComments=Track your deep work and see it as a trail.
DefaultDirName={localappdata}\Programs\Trail
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Trail-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\Trail.exe
UninstallDisplayName=Trail
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "autostart"; Description: "Start Trail automatically when I sign in"
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\Trail\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Trail"; Filename: "{app}\Trail.exe"
Name: "{autodesktop}\Trail"; Filename: "{app}\Trail.exe"; Tasks: desktopicon

[Registry]
; Start at sign-in (the same value the in-app "Startup" checkbox controls)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "Trail"; ValueData: """{app}\Trail.exe"" --minimized"; Tasks: autostart
; Always remove that value on uninstall, even if it was turned on from inside the app
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; \
  ValueName: "Trail"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Trail.exe"; Description: "Open Trail now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im Trail.exe"; Flags: runhidden; RunOnceId: "StopTrail"
