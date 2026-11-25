param(
    [Parameter(Mandatory = $true)][string]$MarkPath,
    [switch]$DevData
)

$ErrorActionPreference = 'Stop'
$mark = (Resolve-Path -LiteralPath $MarkPath).Path
$plugins = Join-Path $mark 'plugins'
if (!(Test-Path -LiteralPath (Join-Path $mark 'core\plugin_loader.py') -PathType Leaf) -or
    !(Test-Path -LiteralPath $plugins -PathType Container)) {
    throw 'Choose the installed Mark LVII folder.'
}
$jarvis = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
if (!(Test-Path -LiteralPath (Join-Path $jarvis '.venv\Scripts\python.exe') -PathType Leaf)) {
    throw 'Set up the JARVIS Python environment first.'
}
$pluginName = 'jarvis_pc_projects'
$config = @{ root = $jarvis; development = [bool]$DevData } | ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $plugins "$pluginName.json"), $config)
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "$pluginName.py") -Destination $plugins
Write-Output 'JARVIS PC & Projects installed. Restart Mark LVII to load it.'
