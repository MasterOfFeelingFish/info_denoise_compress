"""
信息源迁移管理器 - 为老用户自动添加新预设源
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from core.custom_processes.web3digest.utils.logger import setup_logger
from core.custom_processes.web3digest.core.config import settings
from core.custom_processes.web3digest.core.source_manager import SourceManager

logger = setup_logger(__name__)


class SourceMigrationManager:
    """信息源迁移管理器"""

    def __init__(self):
        self.source_manager = SourceManager()
        self.data_dir = Path(settings.DATA_DIR) / "source_migrations"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _get_migration_file(self, user_id: int) -> Path:
        """获取用户迁移状态文件路径"""
        return self.data_dir / f"{user_id}.json"

    async def _get_migration_status(self, user_id: int) -> Dict:
        """获取用户的迁移状态"""
        migration_file = self._get_migration_file(user_id)

        if not migration_file.exists():
            return {
                "last_migrated_version": "v0.0.0",
                "last_migrated_at": None,
                "migrations": []
            }

        try:
            with open(migration_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取迁移状态失败 {user_id}: {e}")
            return {
                "last_migrated_version": "v0.0.0",
                "last_migrated_at": None,
                "migrations": []
            }

    async def _save_migration_status(self, user_id: int, status: Dict) -> bool:
        """保存用户的迁移状态"""
        migration_file = self._get_migration_file(user_id)

        try:
            with open(migration_file, 'w', encoding='utf-8') as f:
                json.dump(status, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"保存迁移状态失败 {user_id}: {e}")
            return False

    async def migrate_user_sources(self, user_id: int) -> Dict:
        """
        为老用户迁移新增的预设源

        Args:
            user_id: 用户ID

        Returns:
            {
                "migrated": 迁移的源数量,
                "new_sources": 新源名称列表,
                "message": 迁移消息
            }
        """

        # 1. 获取当前用户配置
        user_sources = await self.source_manager.get_user_sources(user_id)

        # 2. 检查迁移状态
        migration_status = await self._get_migration_status(user_id)

        # 3. 获取系统当前的预设源
        current_preset = self.source_manager._get_default_preset_sources()

        # 4. 对比找出用户缺少的新源
        # 使用URL作为唯一标识,因为URL是不变的
        existing_urls = {src["url"] for src in user_sources["preset_sources"]}
        new_sources = [
            src for src in current_preset
            if src["url"] not in existing_urls
        ]

        if not new_sources:
            logger.info(f"用户 {user_id} 没有需要迁移的新源")
            return {
                "migrated": 0,
                "new_sources": [],
                "message": "没有新增源需要迁移"
            }

        # 5. 添加新源到用户配置
        user_sources["preset_sources"].extend(new_sources)
        save_success = await self.source_manager.save_user_sources(user_id, user_sources)

        if not save_success:
            logger.error(f"用户 {user_id} 保存迁移配置失败")
            return {
                "migrated": 0,
                "new_sources": [],
                "message": "保存配置失败"
            }

        # 6. 更新迁移状态
        current_time = datetime.now().isoformat()
        migration_status["last_migrated_at"] = current_time
        migration_status["migrations"].append({
            "migrated_at": current_time,
            "added_sources": [src["name"] for src in new_sources],
            "count": len(new_sources)
        })

        await self._save_migration_status(user_id, migration_status)

        logger.info(f"用户 {user_id} 迁移完成,添加了 {len(new_sources)} 个新源")

        return {
            "migrated": len(new_sources),
            "new_sources": [src["name"] for src in new_sources],
            "message": f"已添加 {len(new_sources)} 个新信息源"
        }

    async def check_and_notify(self, user_id: int) -> Dict:
        """
        检查是否有新源可用,返回迁移信息(不自动迁移)

        Args:
            user_id: 用户ID

        Returns:
            {
                "has_new_sources": bool,
                "count": int,
                "new_sources": List[str]
            }
        """

        user_sources = await self.source_manager.get_user_sources(user_id)
        current_preset = self.source_manager._get_default_preset_sources()

        existing_urls = {src["url"] for src in user_sources["preset_sources"]}
        new_sources = [
            src for src in current_preset
            if src["url"] not in existing_urls
        ]

        return {
            "has_new_sources": len(new_sources) > 0,
            "count": len(new_sources),
            "new_sources": [src["name"] for src in new_sources]
        }
