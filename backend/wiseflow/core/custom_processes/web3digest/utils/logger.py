"""
简化日志配置 - 按日期创建独立日志文件，避免导入问题
"""
import sys
import os
from datetime import datetime
from pathlib import Path
from loguru import logger


class DailyLogger:
    """按日期创建独立日志文件的日志器"""

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 当前日期和时间
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.current_time = datetime.now().strftime("%H:%M:%S")

        # 创建每日日志目录
        self.daily_dir = self.data_dir / "logs" / self.current_date
        self.daily_dir.mkdir(parents=True, exist_ok=True)

        # 创建不同类型的日志文件
        self.main_log_file = self.daily_dir / "main.log"
        self.step_log_file = self.daily_dir / "steps.log"
        self.click_log_file = self.daily_dir / "clicks.log"
        self.error_log_file = self.daily_dir / "errors.log"
        self.user_log_file = self.daily_dir / "users.log"

        # 初始化步骤计数器
        self.step_counter = 0
        self.click_counter = 0

        # 设置日志处理器
        self._setup_handlers()

    def _setup_handlers(self):
        """设置日志处理器"""
        # 移除默认处理器
        logger.remove()

        # 控制台输出
        logger.add(
            sys.stdout,
            format="{time:HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="INFO"
        )

        # 主日志文件
        logger.add(
            str(self.main_log_file),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="INFO",
            encoding="utf-8",
            rotation="00:00"  # 每天轮转
        )

        # 错误日志文件
        logger.add(
            str(self.error_log_file),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="ERROR",
            encoding="utf-8"
        )

    def log_step(self, step_name: str, details: dict = None, user_id: int = 0):
        """记录操作步骤"""
        self.step_counter += 1
        timestamp = datetime.now().isoformat()

        step_info = {
            "step_number": self.step_counter,
            "timestamp": timestamp,
            "step_name": step_name,
            "user_id": user_id,
            "details": details or {}
        }

        # 写入步骤日志文件
        try:
            with open(self.step_log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] STEP {self.step_counter}: {step_name}\n")
                if details:
                    f.write(f"  用户ID: {user_id}\n")
                    f.write(f"  详情: {details}\n")
                f.write("-" * 80 + "\n")
        except Exception as e:
            logger.error(f"写入步骤日志失败: {e}")

        # 同时记录到主日志
        logger.info(f"[步骤 {self.step_counter}] {step_name} (用户={user_id})")
        if details:
            logger.debug(f"详情: {details}")

    def log_click(self, user_id: int, callback_data: str, message_text: str = ""):
        """记录按钮点击"""
        self.click_counter += 1
        timestamp = datetime.now().isoformat()

        click_info = {
            "click_number": self.click_counter,
            "timestamp": timestamp,
            "user_id": user_id,
            "callback_data": callback_data,
            "message_text": message_text
        }

        try:
            with open(self.click_log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] CLICK {self.click_counter}:\n")
                f.write(f"  用户ID: {user_id}\n")
                f.write(f"  回调数据: {callback_data}\n")
                if message_text:
                    f.write(f"  消息内容: {message_text}\n")
                f.write("-" * 80 + "\n")
        except Exception as e:
            logger.error(f"写入点击日志失败: {e}")

        logger.info(f"[点击 {self.click_counter}] 用户{user_id} 点击按钮: {callback_data}")

    def log_user_action(self, user_id: int, action: str, details: dict = None):
        """记录用户行为"""
        timestamp = datetime.now().isoformat()

        try:
            with open(self.user_log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] USER ACTION:\n")
                f.write(f"  用户ID: {user_id}\n")
                f.write(f"  行为: {action}\n")
                if details:
                    for key, value in details.items():
                        f.write(f"  {key}: {value}\n")
                f.write("-" * 80 + "\n")
        except Exception as e:
            logger.error(f"写入用户日志失败: {e}")

        logger.info(f"[用户行为] 用户{user_id}: {action}")

    def log_error(self, user_id: int, error_type: str, error_message: str, traceback_str: str = None):
        """记录错误"""
        timestamp = datetime.now().isoformat()

        try:
            with open(self.error_log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] ERROR:\n")
                f.write(f"  用户ID: {user_id}\n")
                f.write(f"  错误类型: {error_type}\n")
                f.write(f"  错误信息: {error_message}\n")
                if traceback_str:
                    f.write(f"  详细堆栈: {traceback_str}\n")
                f.write("=" * 80 + "\n")
        except Exception as e:
            logger.error(f"写入错误日志失败: {e}")

        logger.error(f"[用户{user_id}] {error_type}: {error_message}")

    def log_command(self, user_id: int, command: str, args: list = None):
        """记录命令执行"""
        timestamp = datetime.now().isoformat()

        try:
            with open(self.user_log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] COMMAND:\n")
                f.write(f"  用户ID: {user_id}\n")
                f.write(f"  命令: {command}\n")
                if args:
                    f.write(f"  参数: {args}\n")
                f.write("-" * 80 + "\n")
        except Exception as e:
            logger.error(f"写入命令日志失败: {e}")

        logger.info(f"[命令] 用户{user_id}: {command}")

    def log_conversation_step(self, user_id: int, stage: int, step_name: str, details: dict = None):
        """记录对话步骤"""
        timestamp = datetime.now().isoformat()

        try:
            with open(self.step_log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] CONVERSATION STAGE {stage}: {step_name}\n")
                f.write(f"  用户ID: {user_id}\n")
                if details:
                    for key, value in details.items():
                        f.write(f"  {key}: {value}\n")
                f.write("-" * 80 + "\n")
        except Exception as e:
            logger.error(f"写入对话日志失败: {e}")

        logger.info(f"[对话{stage}] 用户{user_id}: {step_name}")

    def get_current_log_dir(self) -> str:
        """获取当前日志目录路径"""
        return str(self.daily_dir)


# 全局日志器实例
_global_logger = None

def get_daily_logger(data_dir: str = "./data") -> DailyLogger:
    """获取每日日志器实例（单例模式）"""
    global _global_logger
    if _global_logger is None:
        _global_logger = DailyLogger(data_dir)
    return _global_logger

def setup_logger(name: str = None, data_dir: str = "./data"):
    """兼容性函数 - 设置日志"""
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    logger_instance = get_daily_logger(data_dir)
    return logger.bind(name=name) if name else logger


# 便捷的函数调用
def log_user_step(user_id: int, step_name: str, details: dict = None):
    """记录用户步骤（便捷调用）"""
    get_daily_logger().log_step(step_name, details, user_id)

def log_user_click(user_id: int, callback_data: str, message: str = ""):
    """记录用户点击（便捷调用）"""
    get_daily_logger().log_click(user_id, callback_data, message)

def log_user_command(user_id: int, command: str, args: list = None):
    """记录用户命令（便捷调用）"""
    get_daily_logger().log_command(user_id, command, args)

def log_user_error(user_id: int, error_type: str, error_msg: str, traceback: str = None):
    """记录用户错误（便捷调用）"""
    get_daily_logger().log_error(user_id, error_type, error_msg, traceback)
