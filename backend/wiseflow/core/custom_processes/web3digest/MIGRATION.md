# 重构迁移说明

## 重构完成 ✅

`web3digest` 已成功从独立目录重构为 WiseFlow 的一个应用模块。

### 新位置

```
backend/wiseflow/core/custom_processes/web3digest/
```

### 主要变更

1. **目录结构**：从 `backend/web3digest/` 移动到 `backend/wiseflow/core/custom_processes/web3digest/`
2. **导入路径**：所有导入路径已更新为标准 Python 包导入
   - 旧：`from utils.logger import setup_logger`
   - 新：`from core.custom_processes.web3digest.utils.logger import setup_logger`
3. **WiseFlow 集成**：使用标准导入，不再需要 `sys.path.append`
   - 旧：`sys.path.append(str(Path(__file__).parent.parent.parent / "wiseflow" / "core"))`
   - 新：`from core.async_database import AsyncDatabaseManager`
4. **Docker 配置**：已更新，现在只需要一个项目目录

### 运行方式

**从 WiseFlow 项目根目录运行：**

```bash
cd backend/wiseflow
python core/custom_processes/web3digest/main.py
```

### 环境变量

环境变量配置保持不变，在 WiseFlow 项目根目录的 `.env` 文件中配置。

### 数据目录

数据目录路径已更新为：`./data/web3digest`（相对于 WiseFlow 项目根目录）

### 注意事项

- 旧的 `backend/web3digest/` 目录可以删除
- 如果有用户数据需要迁移，请手动复制 `data/` 目录内容到新位置
