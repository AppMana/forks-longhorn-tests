$ErrorActionPreference = 'Stop'
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True
Enable-PSRemoting -SkipNetworkProfileCheck -Force
Set-Item WSMan:\localhost\Service\AllowUnencrypted -Value True
Set-Item WSMan:\localhost\Service\Auth\Basic -Value True
& winrm.cmd set winrm/config/winrs '@{MaxMemoryPerShellMB="2048"}'
& sc.exe config WinRM start= auto
Start-Service WinRM
Set-ExecutionPolicy RemoteSigned -Force
