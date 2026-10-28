; Windows installer for the portable build in dist\AcademicJobTracker (built by packaging/build.py).
; Compile with:  ISCC.exe /DAppVersion=1.0.0 packaging\installer.iss
; Installs for the current user only (no administrator rights needed). Your progress lives in
; %APPDATA%\AcademicJobTracker and is not touched by installing, updating or uninstalling.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{7B0E5B7C-3C1E-4C59-9C1B-4E2B5B8E2A11}
AppName=Academic Job Market Tracker
AppVersion={#AppVersion}
AppPublisher=ZoeHu92
AppPublisherURL=https://github.com/ZoeHu92/Job_Market_Application_Tracker
DefaultDirName={localappdata}\Programs\AcademicJobTracker
DefaultGroupName=Academic Job Market Tracker
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=AcademicJobTracker-{#AppVersion}-windows-setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Academic Job Market Tracker

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[InstallDelete]
; remove the previous version's program files before copying the new ones
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\python"

[Files]
Source: "..\dist\AcademicJobTracker\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Academic Job Market Tracker"; Filename: "{app}\Start Job Tracker.bat"; WorkingDir: "{app}"
Name: "{autodesktop}\Academic Job Market Tracker"; Filename: "{app}\Start Job Tracker.bat"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Start Job Tracker.bat"; Description: "Start the tracker now"; Flags: postinstall nowait skipifsilent shellexec
