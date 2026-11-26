param(
    [Parameter(Mandatory)][ValidateSet('create-key','sign','verify')][string]$Action,
    [string]$PrivateKey,
    [Parameter(Mandatory)][string]$PublicKey,
    [string]$Manifest,
    [string]$Signature
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
$rsaProvider = New-Object System.Security.Cryptography.RSACryptoServiceProvider(3072)
$rsaProvider.PersistKeyInCsp = $false
try {
    if ($Action -eq 'create-key') {
        if ((Test-Path -LiteralPath $PublicKey) -or (Test-Path -LiteralPath $PrivateKey)) { throw 'Choose unused key paths.' }
        $privateBytes = $rsaProvider.ExportCspBlob($true)
        try {
            $protectedBytes = [System.Security.Cryptography.ProtectedData]::Protect($privateBytes, $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
            [System.IO.File]::WriteAllBytes($PrivateKey, $protectedBytes)
            [System.IO.File]::WriteAllText($PublicKey, $rsaProvider.ToXmlString($false))
        } finally { [Array]::Clear($privateBytes, 0, $privateBytes.Length) }
    } elseif ($Action -eq 'sign') {
        $privateBytes = [System.Security.Cryptography.ProtectedData]::Unprotect([System.IO.File]::ReadAllBytes($PrivateKey), $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
        try { $rsaProvider.ImportCspBlob($privateBytes) } finally { [Array]::Clear($privateBytes, 0, $privateBytes.Length) }
        $trustedPublic = [System.IO.File]::ReadAllText($PublicKey).Trim()
        if ($rsaProvider.ToXmlString($false) -cne $trustedPublic) { throw 'The signing key does not match the pinned public key.' }
        $signatureBytes = $rsaProvider.SignData([System.IO.File]::ReadAllBytes($Manifest), 'SHA256')
        [System.IO.File]::WriteAllBytes($Signature, $signatureBytes)
    } else {
        $rsaProvider.FromXmlString([System.IO.File]::ReadAllText($PublicKey))
        if (-not $rsaProvider.VerifyData([System.IO.File]::ReadAllBytes($Manifest), 'SHA256', [System.IO.File]::ReadAllBytes($Signature))) {
            throw 'Release signature mismatch'
        }
    }
} finally { $rsaProvider.Dispose() }
