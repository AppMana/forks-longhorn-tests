param(
    [Parameter(Mandatory = $true)][string]$NodeName,
    [Parameter(Mandatory = $true)][string]$NodeIP,
    [Parameter(Mandatory = $true)][string]$DataMac,
    [Parameter(Mandatory = $true)][ValidateRange(1, 32)][int]$DataPrefixLength,
    [Parameter(Mandatory = $true)][string]$ServerIP,
    [Parameter(Mandatory = $true)][string]$ClusterToken,
    [Parameter(Mandatory = $true)][string]$Rke2Version,
    [Parameter(Mandatory = $true)][ValidateSet('ntfs', 'refs')][string]$Filesystem,
    [string]$Labels = '',
    [string]$Taints = ''
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$bootstrapRoot = 'C:\LonghornTest'
$marker = Join-Path $bootstrapRoot 'complete'
New-Item -ItemType Directory -Path $bootstrapRoot -Force | Out-Null
if (Test-Path $marker) { exit 0 }

$normalizedDataMac = $DataMac.Replace(':', '').Replace('-', '').ToUpperInvariant()
$dataAdapter = Get-NetAdapter | Where-Object {
    $_.MacAddress.Replace('-', '').ToUpperInvariant() -eq $normalizedDataMac
} | Select-Object -First 1
if ($null -eq $dataAdapter) { throw "Data adapter $DataMac did not appear" }
Set-NetIPInterface -InterfaceIndex $dataAdapter.ifIndex -AddressFamily IPv4 -Dhcp Disabled
$configuredDataAddress = Get-NetIPAddress -InterfaceIndex $dataAdapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object IPAddress -eq $NodeIP
if ($null -eq $configuredDataAddress) {
    Get-NetIPAddress -InterfaceIndex $dataAdapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
    New-NetIPAddress -InterfaceIndex $dataAdapter.ifIndex -IPAddress $NodeIP -PrefixLength $DataPrefixLength | Out-Null
}
Write-Host "Configured data adapter $($dataAdapter.Name) as $NodeIP/$DataPrefixLength"

function Invoke-WithRetry {
    param([scriptblock]$Operation, [int]$Attempts = 60, [int]$Delay = 10)
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try { return & $Operation } catch {
            if ($attempt -eq $Attempts) { throw }
            Start-Sleep -Seconds $Delay
        }
    }
}

$feature = Get-WindowsFeature -Name Containers
if (-not $feature.Installed) {
    $result = Install-WindowsFeature -Name Containers -IncludeAllSubFeature
    if ($result.RestartNeeded -eq 'Yes') {
        Restart-Computer -Force
        exit 0
    }
}

Set-Service -Name MSiSCSI -StartupType Automatic
Start-Service -Name MSiSCSI
Rename-Computer -NewName $NodeName -Force -ErrorAction SilentlyContinue

$dataMarker = Join-Path $bootstrapRoot 'data-ready'
if (-not (Test-Path $dataMarker)) {
    Write-Host "Waiting for the $Filesystem Longhorn data disk"
    $disk = $null
    for ($attempt = 1; $attempt -le 60 -and $null -eq $disk; $attempt++) {
        $disk = Get-Disk | Where-Object { -not $_.IsBoot -and -not $_.IsSystem -and $_.PartitionStyle -eq 'RAW' } | Select-Object -First 1
        if ($null -eq $disk) { Start-Sleep -Seconds 2 }
    }
    if ($null -eq $disk) { throw 'Longhorn data disk did not appear' }
    if ($disk.IsOffline) { Set-Disk -Number $disk.Number -IsOffline $false }
    if ($disk.IsReadOnly) { Set-Disk -Number $disk.Number -IsReadOnly $false }
    $disk = Get-Disk -Number $disk.Number
    $partition = $disk | Initialize-Disk -PartitionStyle GPT -PassThru | New-Partition -UseMaximumSize -AssignDriveLetter
    $partition | Format-Volume -FileSystem $Filesystem -NewFileSystemLabel LONGHORN -Confirm:$false -Force | Out-Null
    $mountPath = 'C:\var\lib\longhorn\'
    New-Item -ItemType Directory -Path $mountPath -Force | Out-Null
    $drivePath = "$($partition.DriveLetter):\"
    Remove-PartitionAccessPath -DiskNumber $partition.DiskNumber -PartitionNumber $partition.PartitionNumber -AccessPath $drivePath
    Add-PartitionAccessPath -DiskNumber $partition.DiskNumber -PartitionNumber $partition.PartitionNumber -AccessPath $mountPath
    New-Item -ItemType File -Path $dataMarker -Force | Out-Null
}

$configDirectory = 'C:\etc\rancher\rke2'
New-Item -ItemType Directory -Path $configDirectory -Force | Out-Null
$config = @(
    "server: `"https://$ServerIP`:9345`"",
    "token: `"$ClusterToken`"",
    "node-name: `"$NodeName`"",
    "node-ip: `"$NodeIP`""
)
if ($Labels) {
    $config += 'node-label:'
    $Labels.Split(',') | ForEach-Object { $config += "  - `"$_`"" }
}
if ($Taints) {
    $config += 'node-taint:'
    $Taints.Split(',') | ForEach-Object { $config += "  - `"$_`"" }
}
$config | Set-Content -Path (Join-Path $configDirectory 'config.yaml') -Encoding ascii

$machinePath = [Environment]::GetEnvironmentVariable('Path', [EnvironmentVariableTarget]::Machine)
foreach ($entry in @('C:\var\lib\rancher\rke2\bin', 'C:\usr\local\bin')) {
    if ($machinePath -notlike "*$entry*") { $machinePath += ";$entry" }
}
[Environment]::SetEnvironmentVariable('Path', $machinePath, [EnvironmentVariableTarget]::Machine)
$env:Path = $machinePath

$rke2Path = 'C:\usr\local\bin\rke2.exe'
if (-not (Test-Path $rke2Path)) {
    Write-Host "Installing RKE2 $Rke2Version"
    $installer = Join-Path $bootstrapRoot 'install-rke2.ps1'
    Invoke-WithRetry { Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/rancher/rke2/master/install.ps1' -OutFile $installer }
    & $installer -Method Tar -Type Agent -Version $Rke2Version
    if ($LASTEXITCODE -ne 0) { throw 'RKE2 installation failed' }
}

Write-Host "Waiting for the RKE2 supervisor at $ServerIP"
Invoke-WithRetry {
    & curl.exe --fail --silent --show-error --insecure "https://$ServerIP`:9345/ping" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'RKE2 supervisor is not ready' }
}
if (-not (Get-Service -Name rke2 -ErrorAction SilentlyContinue)) {
    & $rke2Path agent service --add
    if ($LASTEXITCODE -ne 0) { throw 'RKE2 service installation failed' }
}
Set-Service -Name rke2 -StartupType Automatic
Start-Service -Name rke2
New-Item -ItemType File -Path $marker -Force | Out-Null
Write-Host "Windows RKE2 agent provisioning complete"
