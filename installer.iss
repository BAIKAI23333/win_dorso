; Inno Setup script for WinDorso.
; Input:  dist\WinDorso\ (PyInstaller onedir output, see windorso.spec)
; Build:  ISCC.exe installer.iss
; Output: dist\installer\WinDorso-Setup-0.1.0.exe

#define MyAppName "WinDorso"
#define MyAppVersion "0.1.0"
#define MyAppExeName "WinDorso.exe"

[Setup]
AppId={{BE78080B-93B4-4E5A-98A9-BDF7D38A0F56}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=BAIKAI23333
AppPublisherURL=https://github.com/BAIKAI23333/win_dorso
DefaultDirName={localappdata}\Programs\WinDorso
DefaultGroupName=WinDorso
DisableProgramGroupPage=yes
; Per-user install (no admin/UAC prompt) — matches the app's HKCU-only
; registry usage (settings + launch-at-login Run key)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist\installer
OutputBaseFilename=WinDorso-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=assets\win_dorso.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
; 简体中文 installer UI needs the unofficial ChineseSimplified.isl (official
; Inno Setup does not ship Chinese) — drop it into the Inno Setup Languages\
; folder, then uncomment:
; Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\WinDorso\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
