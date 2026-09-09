#ifndef MyAppVersion
  #define MyAppVersion "0.0.2"
#endif

#define MyAppName "DeployDiff"
#define MyAppExeName "DeployDiff.exe"

[Setup]
AppId={{4B3B9F55-C8F6-4E7F-8B8C-9F42F3536E2C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=SeokJun-Bae
AppPublisherURL=https://github.com/SeokJun-Bae/deploydiff
AppSupportURL=https://github.com/SeokJun-Bae/deploydiff/issues
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=DeployDiffSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
