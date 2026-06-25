$ErrorActionPreference = "Stop"

param(
    [Parameter(Mandatory = $true)]
    [string[]] $Path,

    [string] $CertificatePath = $env:FILEZALL_WINDOWS_CERT_PATH,
    [string] $CertificatePassword = $env:FILEZALL_WINDOWS_CERT_PASSWORD,
    [string] $TimestampUrl = $(if ($env:FILEZALL_WINDOWS_TIMESTAMP_URL) { $env:FILEZALL_WINDOWS_TIMESTAMP_URL } else { "http://timestamp.digicert.com" }),
    [string] $Description = "FileZall"
)

if (-not (Get-Command signtool -ErrorAction SilentlyContinue)) {
    throw "signtool.exe is required. Install the Windows SDK and add signtool to PATH."
}

foreach ($Target in $Path) {
    if (-not (Test-Path -LiteralPath $Target)) {
        throw "Cannot sign missing file: $Target"
    }

    $Args = @(
        "sign",
        "/fd", "SHA256",
        "/tr", $TimestampUrl,
        "/td", "SHA256",
        "/d", $Description
    )

    if ($CertificatePath) {
        $Args += @("/f", $CertificatePath)
        if ($CertificatePassword) {
            $Args += @("/p", $CertificatePassword)
        }
    } else {
        $Args += "/a"
    }

    $Args += $Target
    & signtool @Args
    if ($LASTEXITCODE -ne 0) {
        throw "signtool failed for $Target"
    }
}
