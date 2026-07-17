$ErrorActionPreference = 'Stop'
# Packer executes this script and its environment prelude from Windows\Temp.
# Removing those active files makes the provisioner footer fail after the image
# has otherwise been prepared successfully.
Get-ChildItem C:\Windows\Temp -Force -ErrorAction SilentlyContinue |
    Where-Object Name -NotLike 'packer-*' |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force C:\Users\vagrant\AppData\Local\Temp\* -ErrorAction SilentlyContinue
Optimize-Volume -DriveLetter C -ReTrim -Verbose -ErrorAction SilentlyContinue
