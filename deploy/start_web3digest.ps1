# Web3 Daily Digest 启动脚本 (Windows PowerShell)
# 使用方法: .\deploy\start_web3digest.ps1

param(
    [switch]$Test,      # 运行测试模式
    [switch]$Background # 后台运行
)

# 设置控制台编码为 UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

# 获取脚本所在目录
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path $ProjectRoot "backend\wiseflow"
$Web3DigestDir = Join-Path $BackendDir "core\custom_processes\web3digest"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Web3 Daily Digest - 启动脚本" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Python
$PythonPath = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonPath) {
    Write-Host "[ERROR] Python 未安装或未添加到 PATH" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Python: $($PythonPath.Source)" -ForegroundColor Green

# 检查 .env 文件
$EnvFile = Join-Path $Web3DigestDir ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Host "[ERROR] .env 文件不存在: $EnvFile" -ForegroundColor Red
    Write-Host "请复制 env_sample 并配置必要的环境变量" -ForegroundColor Yellow
    exit 1
}
Write-Host "[OK] 配置文件: $EnvFile" -ForegroundColor Green

# 加载环境变量
Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^([^#][^=]+)=(.*)$') {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim()
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
}

# 检查关键环境变量
$RequiredVars = @("TELEGRAM_BOT_TOKEN", "LLM_API_KEY")
foreach ($var in $RequiredVars) {
    $value = [Environment]::GetEnvironmentVariable($var, "Process")
    if ([string]::IsNullOrEmpty($value)) {
        Write-Host "[ERROR] 缺少必要的环境变量: $var" -ForegroundColor Red
        exit 1
    }
    $maskedValue = if ($value.Length -gt 10) { $value.Substring(0, 10) + "..." } else { "***" }
    Write-Host "[OK] $var = $maskedValue" -ForegroundColor Green
}

Write-Host ""

# 切换到工作目录
Set-Location $BackendDir
Write-Host "[INFO] 工作目录: $BackendDir" -ForegroundColor Cyan

if ($Test) {
    # 测试模式
    Write-Host ""
    Write-Host "========== 运行测试 ==========" -ForegroundColor Yellow
    Set-Location $ProjectRoot
    python deploy/test_all.py
} else {
    # 正常启动
    Write-Host ""
    Write-Host "========== 启动服务 ==========" -ForegroundColor Yellow
    
    if ($Background) {
        # 后台运行
        $LogFile = Join-Path $Web3DigestDir "data\web3digest\logs\service.log"
        $LogDir = Split-Path -Parent $LogFile
        if (-not (Test-Path $LogDir)) {
            New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
        }
        
        Write-Host "[INFO] 后台启动，日志文件: $LogFile" -ForegroundColor Cyan
        Start-Process python -ArgumentList "core/custom_processes/web3digest/main.py" `
            -WindowStyle Hidden `
            -RedirectStandardOutput $LogFile `
            -RedirectStandardError $LogFile
        
        Start-Sleep -Seconds 3
        Write-Host "[OK] 服务已在后台启动" -ForegroundColor Green
        Write-Host "[TIP] 查看日志: Get-Content '$LogFile' -Tail 50 -Wait" -ForegroundColor Cyan
    } else {
        # 前台运行
        Write-Host "[INFO] 按 Ctrl+C 停止服务" -ForegroundColor Cyan
        Write-Host ""
        python core/custom_processes/web3digest/main.py
    }
}
