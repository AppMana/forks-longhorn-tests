$ErrorActionPreference = 'Stop'
Remove-Item -Recurse -Force C:\Windows\Temp\* -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force C:\Users\vagrant\AppData\Local\Temp\* -ErrorAction SilentlyContinue
Optimize-Volume -DriveLetter C -ReTrim -Verbose -ErrorAction SilentlyContinue
