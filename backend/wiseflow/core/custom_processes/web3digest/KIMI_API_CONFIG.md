# Kimi API 配置指南

## 📋 概述

本项目已配置为使用 **Kimi API**（Moonshot AI）作为默认的 LLM 服务。Kimi API 使用 OpenAI 兼容接口，支持 `kimi-k2-thinking-preview` 模型。

## 🔑 API Key 配置

### 方式 1：环境变量（推荐）

在 WiseFlow 项目根目录的 `.env` 文件中配置：

```bash
# Kimi API 配置
LLM_API_BASE=https://api.moonshot.cn/v1
LLM_API_KEY=sk-Nu4nsNqZtsD1cmm1hJG2wrgc0eG1cQXe77bxZ226uolR2Idu
PRIMARY_MODEL=kimi-k2-thinking-preview
```

### 方式 2：代码配置

如果需要在代码中直接配置，可以修改 `core/config.py`：

```python
LLM_API_BASE: str = Field("https://api.moonshot.cn/v1", env="LLM_API_BASE")
LLM_API_KEY: str = Field("sk-Nu4nsNqZtsD1cmm1hJG2wrgc0eG1cQXe77bxZ226uolR2Idu", env="LLM_API_KEY")
PRIMARY_MODEL: str = Field("kimi-k2-thinking-preview", env="PRIMARY_MODEL")
```

## 📚 官方文档

- **Kimi K2 思考模型使用指南**: https://platform.moonshot.cn/docs/guide/use-kimi-k2-thinking-model
- **API 平台**: https://platform.moonshot.cn/

## ✅ 验证配置

配置完成后，可以通过以下方式验证：

1. **运行测试脚本**：
   ```bash
   python core/custom_processes/web3digest/test_crawler.py
   ```

2. **启动服务并测试**：
   ```bash
   python core/custom_processes/web3digest/main.py
   ```
   然后在 Telegram Bot 中使用 `/test` 命令测试完整流程。

## 🔄 切换到其他 LLM 服务

如果需要使用其他 LLM 服务（如 SiliconFlow、DeepSeek 等），只需修改 `.env` 文件：

```bash
# 使用 SiliconFlow
LLM_API_BASE=https://api.siliconflow.cn/v1
LLM_API_KEY=your_siliconflow_api_key
PRIMARY_MODEL=Qwen/Qwen2.5-32B-Instruct

# 或使用 DeepSeek
LLM_API_BASE=https://api.deepseek.com/v1
LLM_API_KEY=your_deepseek_api_key
PRIMARY_MODEL=deepseek-chat
```

## ⚙️ 高级配置

### 并发数配置

```bash
# 同时处理的 LLM 请求数（默认 3）
LLM_CONCURRENT_NUMBER=3
```

### 模型参数

Kimi API 支持标准的 OpenAI 参数：
- `temperature`: 控制输出随机性（0-1）
- `max_tokens`: 最大输出 token 数
- `top_p`: 核采样参数

这些参数在 `llm_client.py` 中已配置，可根据需要调整。

## 🛠️ 故障排查

### 问题 1：API Key 无效

**症状**：`401 Unauthorized` 错误

**解决**：
1. 检查 API Key 是否正确
2. 确认 API Key 是否已激活
3. 访问 https://platform.moonshot.cn/ 验证账户状态

### 问题 2：模型不存在

**症状**：`404 Model not found` 错误

**解决**：
1. 确认模型名称正确：`kimi-k2-thinking-preview`
2. 检查 API Key 是否有权限使用该模型
3. 查看官方文档确认模型可用性

### 问题 3：请求超时

**症状**：请求长时间无响应

**解决**：
1. 检查网络连接
2. 降低并发数：`LLM_CONCURRENT_NUMBER=1`
3. 增加超时时间（在代码中配置）

## 📝 注意事项

1. **API Key 安全**：不要将 API Key 提交到代码仓库，使用 `.env` 文件并添加到 `.gitignore`
2. **使用限制**：注意 API 的调用频率和配额限制
3. **成本控制**：Kimi API 按 token 计费，注意控制使用量

## 🔗 相关链接

- [Kimi 开放平台](https://platform.moonshot.cn/)
- [API 文档](https://platform.moonshot.cn/docs)
- [使用指南](https://platform.moonshot.cn/docs/guide/use-kimi-k2-thinking-model)
