param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$HostName,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$UserName,
    [Parameter(Mandatory = $true)]
    [string]$RemoteDatabase,
    [Parameter(Mandatory = $true)]
    [string]$RemotePython,
    [Parameter(Mandatory = $true)]
    [string]$RemoteServer
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function ConvertTo-PosixLiteral {
    param([Parameter(Mandatory = $true)][string]$Value)

    if ($Value -match "['`r`n]") {
        throw 'Remote paths must not contain apostrophes or line breaks.'
    }
    return "'$Value'"
}

# Authentication is deliberately delegated to OpenSSH key handling or ~/.ssh/config.
# The remote launch command travels inside the encrypted SSH stream, not process arguments.
$database = ConvertTo-PosixLiteral $RemoteDatabase
$python = ConvertTo-PosixLiteral $RemotePython
$server = ConvertTo-PosixLiteral $RemoteServer
$remoteScript = @"
export WHO_ICTRP_DB=$database
exec $python $server
"@

$remoteScript | & ssh -T -- "$UserName@$HostName" 'sh -s'
exit $LASTEXITCODE
