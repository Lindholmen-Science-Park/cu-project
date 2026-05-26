# Refresh PATH and test Ollama
# Run this in PowerShell if ollama command doesn't work

$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
Write-Host "PATH refreshed. Testing Ollama..."
ollama --version

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ Ollama is working! You can now run 'starttraining.bat'" -ForegroundColor Green
} else {
    Write-Host "`n❌ Ollama still not found. Try:" -ForegroundColor Red
    Write-Host "1. Close and reopen PowerShell completely"
    Write-Host "2. Or use: `"%USERPROFILE%\AppData\Local\Programs\Ollama\ollama.exe`" --version"
}

