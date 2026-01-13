# Web3 Daily Digest 停止脚本 (Windows PowerShell)

Write-Host "Stopping Web3 Daily Digest..." -ForegroundColor Yellow

# 查找并停止 Python 进程
$processes = Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*web3digest*" -or $_.CommandLine -like "*main.py*"
}

if ($processes) {
    $processes | Stop-Process -Force
    Write-Host "Service stopped." -ForegroundColor Green
} else {
    # 尝试停止所有相关 Python 进程
    $allPython = Get-Process python -ErrorAction SilentlyContinue
    if ($allPython) {
        Write-Host "Found Python processes, stopping all..." -ForegroundColor Yellow
        $allPython | Stop-Process -Force
        Write-Host "All Python processes stopped." -ForegroundColor Green
    } else {
        Write-Host "No running service found." -ForegroundColor Cyan
    }
}
