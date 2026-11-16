; UniBoard installer (Inno Setup 6)
; Build: ISCC.exe uniboard.iss  (expects dist\UniBoard.exe to exist)

#define AppName "UniBoard"
#ifndef AppVersion
  #define AppVersion "0.9.0"
#endif
#define AppExe "UniBoard.exe"

[Setup]
AppId={{8F2A6C51-7E34-4B8D-9A55-2C1D10D34E11}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=GoldensHQ
AppPublisherURL=https://github.com/GoldensHQ/UniBoard
AppSupportURL=https://github.com/GoldensHQ/UniBoard/issues
DefaultDirName={localappdata}\Programs\UniBoard
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=dist
OutputBaseFilename=UniBoard-Setup-{#AppVersion}
SetupIconFile=assets\uniboard.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Per-user install: no admin rights, no UAC prompt
PrivilegesRequired=lowest
CloseApplications=yes
LicenseFile=LICENSE

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; \
    GroupDescription: "Additional icons:"; Flags: unchecked
Name: "autostart"; Description: "Start UniBoard when Windows &starts"; \
    GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\logo.svg"; DestDir: "{app}\assets"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "{#AppName}"; \
    ValueData: """{app}\{#AppExe}"""; Tasks: autostart; \
    Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "&Launch UniBoard"; \
    Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM {#AppExe} /F"; Flags: runhidden; RunOnceId: "KillApp"

[UninstallDelete]
; User data in %APPDATA%\UniBoard is kept on purpose (clipboard history).
