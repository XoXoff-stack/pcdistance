#define AppName "PC Distance"
#define AppVersion "2.0.0"
#define AppPublisher "PC Distance"
#define AppExeName "PCDistance.exe"

[Setup]
AppId={{A8E1E4C5-60B0-4D8F-9B61-7D72A9C1F251}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\PCDistance
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist
OutputBaseFilename=PCDistance-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "dist\PCDistance\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\PC Distance"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\PC Distance"; Filename: "{app}\{#AppExeName}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Lancer PC Distance"; Flags: postinstall nowait skipifsilent
