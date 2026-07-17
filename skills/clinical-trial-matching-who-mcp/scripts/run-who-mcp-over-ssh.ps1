param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,
    [Parameter(Mandatory = $true)]
    [string]$UserName,
    [Parameter(Mandatory = $true)]
    [string]$RemoteDatabase,
    [Parameter(Mandatory = $true)]
    [string]$RemotePython,
    [Parameter(Mandatory = $true)]
    [string]$RemoteServer
)

$remote = "env WHO_ICTRP_DB='$RemoteDatabase' '$RemotePython' '$RemoteServer'"
& ssh -T "$UserName@$HostName" $remote
exit $LASTEXITCODE