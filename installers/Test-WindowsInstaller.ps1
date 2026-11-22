param(
    [Parameter(Mandatory)]
    [string]$Installer,
    [Parameter(Mandatory)]
    [string]$EvidenceDirectory
)

$ErrorActionPreference = 'Stop'
$installerPath = (Resolve-Path -LiteralPath $Installer).Path
$evidence = (New-Item -ItemType Directory -Path $EvidenceDirectory -Force).FullName
$appId = '{C55EB66E-3D4F-47B9-8804-01975A9740E1}_is1'
$uninstallKey = "Software\Microsoft\Windows\CurrentVersion\Uninstall\$appId"
foreach ($hive in @('HKCU', 'HKLM')) {
    foreach ($view in @('', 'WOW6432Node\')) {
        $key = "${hive}:\Software\${view}Microsoft\Windows\CurrentVersion\Uninstall\$appId"
        if (Test-Path -LiteralPath $key) { throw 'Use a clean Windows account without an existing JARVIS installation.' }
    }
}

function Invoke-CheckedProcess($File, [string[]]$Arguments, $Stage) {
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "$Stage exited with code $($process.ExitCode)." }
    Write-Output "$Stage passed."
}

$root = Join-Path ([IO.Path]::GetTempPath()) ('jarvis-acceptance-' + [guid]::NewGuid().ToString('N'))
$appDir = Join-Path $root 'application'
$profile = Join-Path $root 'profile'
New-Item -ItemType Directory -Path (Join-Path $profile 'JarvisAI') -Force | Out-Null
$marker = Join-Path $profile 'JarvisAI\keep-data.txt'
Set-Content -LiteralPath $marker -Value 'JARVIS acceptance profile'
$previousLocalAppData = $env:LOCALAPPDATA
$env:LOCALAPPDATA = $profile

try {
    Invoke-CheckedProcess $installerPath @('/SP-', '/VERYSILENT', '/SUPPRESSMSGBOXES',
        '/NORESTART', '/NOCLOSEAPPLICATIONS', "/DIR=`"$appDir`"", '/TASKS=',
        "/LOG=`"$(Join-Path $evidence 'install.log')`"") 'Clean install'
    $installed = Join-Path $appDir 'JarvisAI.exe'
    if (!(Test-Path -LiteralPath $installed -PathType Leaf)) { throw 'Installed executable is missing.' }
    if (!(Test-Path -LiteralPath "HKCU:\$uninstallKey")) { throw 'Per-user uninstall registration is missing.' }
    Invoke-CheckedProcess $installed @('--smoke-test') 'Installed HUD startup'
    Invoke-CheckedProcess $installed @('--check-voice-runtime') 'Installed voice dependencies'
    if (!(Test-Path -LiteralPath (Join-Path $profile 'JarvisAI\history.sqlite3'))) {
        throw 'The installed application did not initialize its test profile.'
    }
} finally {
    try {
        $uninstallers = @(Get-ChildItem -LiteralPath $appDir -Filter 'unins*.exe' -File -ErrorAction SilentlyContinue)
        if ($uninstallers.Count -eq 1) {
            Invoke-CheckedProcess $uninstallers[0].FullName @('/VERYSILENT', '/SUPPRESSMSGBOXES',
                '/NORESTART', "/LOG=`"$(Join-Path $evidence 'uninstall.log')`"") 'Uninstall'
        }
    } finally {
        $env:LOCALAPPDATA = $previousLocalAppData
    }
}

if ($uninstallers.Count -ne 1 -or (Test-Path -LiteralPath $installed) -or
        (Test-Path -LiteralPath "HKCU:\$uninstallKey")) {
    throw 'Uninstall did not remove the executable and uninstall registration.'
}
if (!(Test-Path -LiteralPath $marker) -or
        !(Test-Path -LiteralPath (Join-Path $profile 'JarvisAI\history.sqlite3'))) {
    throw 'Uninstall did not preserve the test profile.'
}
Remove-Item -LiteralPath $root -Recurse -Force
Write-Output 'Verified clean install, installed startup, uninstall, and profile retention.'
