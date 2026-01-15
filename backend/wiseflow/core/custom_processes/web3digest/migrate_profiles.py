"""
迁移用户画像脚本
将旧目录的画像文件迁移到新目录
"""
import os
import shutil
from pathlib import Path

# 源目录（旧）
source_dir = Path(__file__).parent.parent.parent.parent / "data" / "profiles"

# 目标目录（新）
target_dir = Path(__file__).parent / "data" / "web3digest" / "profiles"

print(f"源目录: {source_dir}")
print(f"目标目录: {target_dir}")

# 确保目标目录存在
target_dir.mkdir(parents=True, exist_ok=True)

# 迁移所有画像文件
migrated_count = 0
for file_path in source_dir.glob("*"):
    if file_path.is_file():
        target_file = target_dir / file_path.name
        
        # 如果目标文件已存在，跳过
        if target_file.exists():
            print(f"跳过 {file_path.name}（已存在）")
            continue
        
        # 复制文件
        shutil.copy2(file_path, target_file)
        print(f"迁移 {file_path.name}")
        migrated_count += 1

print(f"\n迁移完成！共迁移 {migrated_count} 个文件")
