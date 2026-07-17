$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$virtioImage = 'C:\Windows\Temp\virtio-win.iso'
if (-not $env:PACKER_HTTP_ADDR) {
    throw 'PACKER_HTTP_ADDR is unavailable; configure QEMU http_directory with the pinned virtio-win.iso'
}
Invoke-WebRequest -UseBasicParsing -Uri "http://$($env:PACKER_HTTP_ADDR)/virtio-win.iso" -OutFile $virtioImage
$actualChecksum = (Get-FileHash -Algorithm SHA256 -Path $virtioImage).Hash
if ($actualChecksum -ne $env:VIRTIO_ISO_CHECKSUM) {
    throw "virtio-win ISO checksum mismatch: expected $($env:VIRTIO_ISO_CHECKSUM), got $actualChecksum"
}
Mount-DiskImage -ImagePath $virtioImage | Out-Null
$virtio = Get-DiskImage -ImagePath $virtioImage | Get-Volume
$virtioRoot = "$($virtio.DriveLetter):\"
Get-ChildItem -Path $virtioRoot -Filter '*.inf' -Recurse | ForEach-Object {
    & pnputil.exe /add-driver $_.FullName /install | Out-Null
}

$guestAgent = Join-Path $virtioRoot 'guest-agent\qemu-ga-x86_64.msi'
if (Test-Path $guestAgent) {
    Start-Process msiexec.exe -ArgumentList '/i', "`"$guestAgent`"", '/qn', '/norestart' -Wait
}
Dismount-DiskImage -ImagePath $virtioImage
Remove-Item -Force $virtioImage

Install-WindowsFeature -Name Containers -IncludeAllSubFeature | Out-Null
Set-Service MSiSCSI -StartupType Automatic
Start-Service MSiSCSI
Install-WindowsFeature -Name OpenSSH-Server -ErrorAction SilentlyContinue | Out-Null
if (Get-Service sshd -ErrorAction SilentlyContinue) {
    Set-Service sshd -StartupType Automatic
    Start-Service sshd
}

# Keep the production security posture while preventing an update-triggered
# reboot from invalidating a deterministic test run.
$updatePolicy = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU'
New-Item -Path $updatePolicy -Force | Out-Null
New-ItemProperty -Path $updatePolicy -Name NoAutoRebootWithLoggedOnUsers -PropertyType DWord -Value 1 -Force | Out-Null
New-NetFirewallRule -DisplayName 'RKE2 supervisor' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 9345 -ErrorAction SilentlyContinue | Out-Null
New-NetFirewallRule -DisplayName 'Kubernetes API' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 6443 -ErrorAction SilentlyContinue | Out-Null

if ((Get-ComputerInfo).WindowsProductName -notlike '*Server*') { throw 'the image is not Windows Server' }
