<# Signs an existing EXE/MSI using an installed, trusted publisher certificate.
Does not build, purchase a certificate, export a key or modify trust stores. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ArtifactPath,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-fA-F0-9]{40}$')][string]$CertificateThumbprint,
    [Parameter(Mandatory=$true)][uri]$TimestampUrl,
    [string]$SignToolPath = 'signtool.exe'
)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Windows is required for Authenticode signing.' }
if ($TimestampUrl.Scheme -ne 'https') { throw 'Use your certificate provider HTTPS RFC3161 timestamp URL.' }
$artifact = Get-Item -LiteralPath $ArtifactPath
if ($artifact.PSIsContainer) { throw 'Artifact must be an existing file.' }
if ($artifact.Extension.ToLowerInvariant() -notin @('.exe', '.msi', '.dll')) {
    throw 'Only existing EXE, MSI or DLL artifacts are supported.'
}
$cert = Get-Item -LiteralPath "Cert:\CurrentUser\My\$CertificateThumbprint"
if (-not $cert.HasPrivateKey) { throw 'The certificate has no accessible private key.' }
if ($cert.NotAfter -lt (Get-Date) -or $cert.NotBefore -gt (Get-Date)) { throw 'Certificate is not currently valid.' }
$codeSigningOid = '1.3.6.1.5.5.7.3.3'
$ekuOids = @($cert.Extensions | Where-Object { $_ -is [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension] } | ForEach-Object { $_.EnhancedKeyUsages } | ForEach-Object { $_.Value })
if ($codeSigningOid -notin $ekuOids) {
    throw 'Certificate does not include Code Signing usage.'
}
$chain = New-Object System.Security.Cryptography.X509Certificates.X509Chain
try {
    $chain.ChainPolicy.RevocationMode = 'Online'
    if (-not $chain.Build($cert)) { throw 'Certificate chain is not trusted or revocation checking failed.' }
} finally { $chain.Dispose() }
$tool = (Get-Command $SignToolPath -ErrorAction Stop).Source
& $tool sign /sha1 $CertificateThumbprint /s My /fd SHA256 /tr $TimestampUrl.AbsoluteUri /td SHA256 /d 'Jarvis-Blue' $artifact.FullName
if ($LASTEXITCODE -ne 0) { throw "SignTool failed with exit code $LASTEXITCODE." }
& $tool verify /pa /all /v $artifact.FullName
if ($LASTEXITCODE -ne 0) { throw 'Authenticode verification failed.' }
$result = Get-AuthenticodeSignature -LiteralPath $artifact.FullName
if ($result.Status -ne 'Valid' -or $result.SignerCertificate.Thumbprint -ne $cert.Thumbprint) {
    throw 'Final signature does not match the selected trusted publisher certificate.'
}
Write-Host "Jarvis-Blue signature verified. Publisher: $($result.SignerCertificate.Subject)"
