# Powershell script to start ngrok
$ngrokPath = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe"
# Using http 5000 (Flask default) instead of tcp
& $ngrokPath http 5000
