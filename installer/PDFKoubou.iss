; PDF工房 インストーラー（Inno Setup 6）
; 作り方：build.bat で dist\PDFKoubou を作ってから、build_installer.bat を実行

#define AppName "PDF工房"
#define AppVersion "1.4"
#define AppExe "PDFKoubou.exe"
#define SrcDir "..\dist\PDFKoubou"

[Setup]
AppId={{2CF60D53-0281-42C1-8B10-CBA08C6A4EDD}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Astras Group
AppPublisherURL=https://astras-tokushima.com/
AppSupportURL=https://astras-tokushima.com/
AppContact=info@astras-tokushima.com
AppCopyright=Copyright (C) 2026 Astras Group / AGPL-3.0
LicenseFile=license_ja.txt
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} セットアップ
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; 管理者権限なしで入れられる（ユーザーごと）。必要ならすべてのユーザー向けも選べる
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=output
OutputBaseFilename=PDF工房_セットアップ_{#AppVersion}
SetupIconFile=..\pdf_koubou\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
ChangesAssociations=yes

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにアイコンを作る"; GroupDescription: "アイコン:"
Name: "openwith"; Description: "PDF・Office・画像ファイルの「プログラムから開く」に PDF工房 を追加する（既定のアプリは変わりません）"; GroupDescription: "ファイルとの関連付け:"

[Files]
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "license_ja.txt"; DestDir: "{app}"; DestName: "利用条件.txt"; Flags: ignoreversion
Source: "インストールの手引き.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\PDFKoubou.ico"
Name: "{group}\{#AppName} の利用条件とライセンス"; Filename: "{app}\licenses"
Name: "{group}\{#AppName} をアンインストール"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\PDFKoubou.ico"; Tasks: desktopicon

[Registry]
; アプリの登録（「プログラムから開く」で表示される名前とアイコン）
Root: HKA; Subkey: "Software\Classes\PDFKoubou.Document"; ValueType: string; ValueName: ""; ValueData: "{#AppName} で開くファイル"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\PDFKoubou.Document\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\PDFKoubou.ico"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\PDFKoubou.Document\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: openwith
; 「プログラムから開く」の候補に追加（既定は変更しない）
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "PDFKoubou.Document"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.docx\OpenWithProgids"; ValueType: string; ValueName: "PDFKoubou.Document"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.doc\OpenWithProgids"; ValueType: string; ValueName: "PDFKoubou.Document"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.xlsx\OpenWithProgids"; ValueType: string; ValueName: "PDFKoubou.Document"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.xls\OpenWithProgids"; ValueType: string; ValueName: "PDFKoubou.Document"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.pptx\OpenWithProgids"; ValueType: string; ValueName: "PDFKoubou.Document"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.ppt\OpenWithProgids"; ValueType: string; ValueName: "PDFKoubou.Document"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.jpg\OpenWithProgids"; ValueType: string; ValueName: "PDFKoubou.Document"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.jpeg\OpenWithProgids"; ValueType: string; ValueName: "PDFKoubou.Document"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.png\OpenWithProgids"; ValueType: string; ValueName: "PDFKoubou.Document"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.txt\OpenWithProgids"; ValueType: string; ValueName: "PDFKoubou.Document"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith

[Run]
Filename: "{app}\{#AppExe}"; Description: "PDF工房 を起動する"; Flags: nowait postinstall skipifsilent
