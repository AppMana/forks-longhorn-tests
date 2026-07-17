$ErrorActionPreference = 'Stop'
Remove-Item -Recurse -Force C:\Windows\Temp\* -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force C:\Users\vagrant\AppData\Local\Temp\* -ErrorAction SilentlyContinue
Optimize-Volume -DriveLetter C -ReTrim -Verbose -ErrorAction SilentlyContinue
# Leave shutdown to Packer. If Sysprep powers the guest off itself, Packer treats
# the vanished WinRM endpoint as a failed shutdown and discards the valid image.
$sysprep = Start-Process `
    -FilePath C:\Windows\System32\Sysprep\Sysprep.exe `
    -ArgumentList '/generalize', '/oobe', '/quit', '/quiet' `
    -Wait `
    -PassThru
if ($sysprep.ExitCode -ne 0) {
    throw "Sysprep failed with exit code $($sysprep.ExitCode)"
}
