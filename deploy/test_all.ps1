# Web3 Daily Digest - 完整测试脚本
# 使用方法: .\deploy\test_all.ps1

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path $ProjectRoot "backend\wiseflow"
$Web3DigestDir = Join-Path $BackendDir "core\custom_processes\web3digest"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Web3 Daily Digest - 完整测试" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# 加载环境变量
$EnvFile = Join-Path $Web3DigestDir ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^([^#][^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
    Write-Host "[OK] 环境变量已加载" -ForegroundColor Green
}

Set-Location $BackendDir

Write-Host ""
Write-Host "========== 测试 1: 配置验证 ==========" -ForegroundColor Yellow
python -c @"
from dotenv import load_dotenv
load_dotenv('core/custom_processes/web3digest/.env')
from core.custom_processes.web3digest.core.config import settings
print(f'  LLM_API_BASE: {settings.LLM_API_BASE}')
print(f'  PRIMARY_MODEL: {settings.PRIMARY_MODEL}')
print(f'  DAILY_PUSH_TIME: {settings.DAILY_PUSH_TIME}')
print('[OK] 配置验证通过')
"@

Write-Host ""
Write-Host "========== 测试 2: LLM 连接 ==========" -ForegroundColor Yellow
python -c @"
import asyncio
from dotenv import load_dotenv
load_dotenv('core/custom_processes/web3digest/.env')
from core.custom_processes.web3digest.core.llm_client import LLMClient

async def test():
    client = LLMClient()
    response = await client.complete('Say OK', max_tokens=10)
    print(f'  LLM Response: {response}')
    print('[OK] LLM 连接成功')

asyncio.run(test())
"@

Write-Host ""
Write-Host "========== 测试 3: RSS 抓取 ==========" -ForegroundColor Yellow
python -c @"
import asyncio
from dotenv import load_dotenv
load_dotenv('core/custom_processes/web3digest/.env')
from core.custom_processes.web3digest.core.wiseflow_client import WiseFlowClient

async def test():
    client = WiseFlowClient()
    await client.initialize()
    sources = [{'url': 'https://cointelegraph.com/rss', 'name': 'Test', 'enabled': True}]
    result = await client.trigger_crawl(sources=sources)
    print(f'  Status: {result[\"status\"]}')
    print(f'  Articles: {result[\"articles_count\"]}')
    print('[OK] RSS 抓取成功' if result['status'] == 0 else '[FAIL] RSS 抓取失败')

asyncio.run(test())
"@

Write-Host ""
Write-Host "========== 测试 4: 数据存储 ==========" -ForegroundColor Yellow
python -c @"
import asyncio
from dotenv import load_dotenv
load_dotenv('core/custom_processes/web3digest/.env')
from core.custom_processes.web3digest.core.user_manager import UserManager

async def test():
    manager = UserManager()
    is_new = await manager.register_user(12345, 'TestUser')
    user = await manager.get_user(12345)
    if user:
        print(f'  User ID: {user[\"id\"]}')
        print(f'  User Name: {user[\"name\"]}')
        print('[OK] 数据存储成功')
    else:
        print('[FAIL] 数据存储失败')

asyncio.run(test())
"@

Write-Host ""
Write-Host "========== 测试 5: 信息源管理 ==========" -ForegroundColor Yellow
python -c @"
import asyncio
from dotenv import load_dotenv
load_dotenv('core/custom_processes/web3digest/.env')
from core.custom_processes.web3digest.core.source_manager import SourceManager

async def test():
    manager = SourceManager()
    sources = await manager.get_user_sources(12345)
    preset_count = len(sources['preset_sources'])
    custom_count = len(sources['custom_sources'])
    print(f'  Preset sources: {preset_count}')
    print(f'  Custom sources: {custom_count}')
    print('[OK] 信息源管理正常')

asyncio.run(test())
"@

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  测试完成!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "下一步: 启动服务后在 Telegram 中发送 /test 进行完整测试" -ForegroundColor Yellow
