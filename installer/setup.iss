#define AppName "Конструктор шахматных диаграмм"
#define AppExe "ChessDiagramConstructor.exe"
[Setup]
AppId={{DE7A936B-263B-4ADB-8E6C-79E2D4E1F018}
AppName={#AppName}
AppVersion=0.2.0
AppPublisher=ChessDiagramConstructor
DefaultDirName={localappdata}\Programs\ChessDiagramConstructor
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release
OutputBaseFilename=ChessDiagramConstructor_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile=..\LICENSE
[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; Flags: checkedonce
[Files]
Source: "..\dist\ChessDiagramConstructor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
[Registry]
Root: HKCU; Subkey: "Software\Classes\.chessdiagram\OpenWithProgids"; ValueType: string; ValueName: "ChessDiagramConstructor.Project"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\ChessDiagramConstructor.Project"; ValueType: string; ValueName: ""; ValueData: "Шахматная диаграмма"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\ChessDiagramConstructor.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"
Root: HKCU; Subkey: "Software\Classes\ChessDiagramConstructor.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""
[Run]
Filename: "{app}\{#AppExe}"; Description: "Запустить программу"; Flags: nowait postinstall skipifsilent
