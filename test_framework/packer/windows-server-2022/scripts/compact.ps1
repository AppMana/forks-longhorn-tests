$ErrorActionPreference = 'Stop'
Remove-Item -Recurse -Force C:\Windows\Temp\* -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force C:\Users\vagrant\AppData\Local\Temp\* -ErrorAction SilentlyContinue
Optimize-Volume -DriveLetter C -ReTrim -Verbose -ErrorAction SilentlyContinue
& C:\Windows\System32\Sysprep\Sysprep.exe /generalize /oobe /shutdown /quiet
