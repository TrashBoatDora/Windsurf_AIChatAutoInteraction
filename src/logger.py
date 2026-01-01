# -*- coding: utf-8 -*-
"""
Hybrid UI Automation Script - 日誌系統模組
提供詳細的日誌記錄功能，包含成功/失敗/錯誤追蹤
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 導入配置
sys.path.append(str(Path(__file__).parent.parent))
try:
    from config.config import config
except ImportError:
    try:
        from config import config
    except ImportError:
        import sys
        sys.path.append(str(Path(__file__).parent.parent / "config"))
        import config

class AutomationLogger:
    """自動化腳本專用日誌記錄器"""
    
    def __init__(self, name: str = "AutomationScript", log_file: Optional[str] = None):
        """
        初始化日誌記錄器
        
        Args:
            name: 日誌記錄器名稱
            log_file: 自定義日誌檔案路徑
        """
        self.name = name
        self.logger = logging.getLogger(name)
        # 確保日誌級別正確設定
        log_level = getattr(logging, config.LOG_LEVEL, logging.INFO)
        self.logger.setLevel(log_level)
        
        # 清除已存在的處理器，避免重複
        self.logger.handlers.clear()
        
        # 設定日誌檔案路徑
        if log_file:
            self.log_file = Path(log_file)
        else:
            self.log_file = config.get_log_file_path()
        
        # 確保日誌目錄存在
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 設定格式器
        formatter = logging.Formatter(config.LOG_FORMAT)
        
        # 設定檔案處理器
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        
        # 設定控制台處理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # 記錄日誌系統啟動
        self.info(f"日誌系統初始化完成 - 檔案: {self.log_file}")
    
    def debug(self, message: str, exc_info: bool = False):
        """記錄除錯訊息"""
        self.logger.debug(message, exc_info=exc_info)
    
    def info(self, message: str, exc_info: bool = False):
        """記錄一般訊息"""
        self.logger.info(message, exc_info=exc_info)
    
    def warning(self, message: str, exc_info: bool = False):
        """記錄警告訊息"""
        self.logger.warning(message, exc_info=exc_info)
    
    def error(self, message: str, exc_info: bool = False):
        """記錄錯誤訊息"""
        self.logger.error(message, exc_info=exc_info)
    
    def critical(self, message: str, exc_info: bool = False):
        """記錄嚴重錯誤訊息"""
        self.logger.critical(message, exc_info=exc_info)
    
    def project_start(self, project_path: str):
        """記錄專案開始處理"""
        self.info(f"🚀 開始處理專案: {project_path}")
    
    def project_success(self, project_path: str, elapsed_time: float = None):
        """記錄專案處理成功"""
        time_info = f" (耗時: {elapsed_time:.2f}秒)" if elapsed_time else ""
        self.info(f"✅ 專案處理成功: {project_path}{time_info}")
    
    def project_failed(self, project_path: str, error_msg: str, elapsed_time: float = None):
        """記錄專案處理失敗"""
        time_info = f" (耗時: {elapsed_time:.2f}秒)" if elapsed_time else ""
        self.error(f"❌ 專案處理失敗: {project_path}{time_info} - 錯誤: {error_msg}")
    
    def copilot_interaction(self, action: str, status: str = "INFO", details: str = ""):
        """記錄 Copilot 互動"""
        emoji = {"INFO": "ℹ️", "SUCCESS": "✅", "ERROR": "❌", "WARNING": "⚠️"}.get(status, "ℹ️")
        message = f"{emoji} Copilot {action}"
        if details:
            message += f" - {details}"
        
        if status == "ERROR":
            self.error(message)
        elif status == "WARNING":
            self.warning(message)
        else:
            self.info(message)
    
    def ui_action(self, action: str, status: str = "INFO", details: str = ""):
        """記錄 UI 操作"""
        emoji = {"INFO": "🖱️", "SUCCESS": "✅", "ERROR": "❌", "WARNING": "⚠️"}.get(status, "🖱️")
        message = f"{emoji} UI操作: {action}"
        if details:
            message += f" - {details}"
        
        if status == "ERROR":
            self.error(message)
        elif status == "WARNING":
            self.warning(message)
        else:
            self.info(message)
    
    def image_recognition(self, image_name: str, found: bool, confidence: float = None):
        """記錄圖像識別結果"""
        status = "找到" if found else "未找到"
        confidence_info = f" (信心度: {confidence:.2f})" if confidence else ""
        emoji = "🔍✅" if found else "🔍❌"
        self.info(f"{emoji} 圖像識別: {image_name} - {status}{confidence_info}")
    
    def batch_summary(self, total: int, success: int, failed: int, elapsed_time: float):
        """記錄批次處理摘要"""
        success_rate = (success / total * 100) if total > 0 else 0
        self.info(f"📊 批次處理完成:")
        self.info(f"   總專案數: {total}")
        self.info(f"   成功: {success}")
        self.info(f"   失敗: {failed}")
        self.info(f"   成功率: {success_rate:.1f}%")
        self.info(f"   總耗時: {elapsed_time:.2f}秒")
    
    def emergency_stop(self, reason: str):
        """記錄緊急停止"""
        self.critical(f"🛑 緊急停止 - 原因: {reason}")
    
    def retry_attempt(self, project_path: str, attempt: int, max_attempts: int):
        """記錄重試嘗試"""
        self.warning(f"🔄 重試專案: {project_path} (第 {attempt}/{max_attempts} 次)")
    
    def create_separator(self, title: str = ""):
        """創建分隔線"""
        separator = "=" * 60
        if title:
            title_padded = f" {title} "
            separator = separator[:25] + title_padded + separator[25+len(title_padded):]
        self.info(separator)
    
    def get_log_file_path(self) -> str:
        """取得日誌檔案路徑"""
        return str(self.log_file)

class ProjectLogger:
    """單一專案專用日誌記錄器"""
    
    def __init__(self, project_name: str, main_logger: AutomationLogger):
        """
        初始化專案日誌記錄器
        
        Args:
            project_name: 專案名稱
            main_logger: 主日誌記錄器
        """
        self.project_name = project_name
        self.main_logger = main_logger
        self.start_time = datetime.now()

        # 在 ExecutionResult/AutomationLog 資料夾下創建專用日誌檔案（使用 config 設定）
        try:
            from config.config import config
            automation_log_dir = config.EXECUTION_RESULT_DIR / "AutomationLog"
        except ImportError:
            script_root = Path(__file__).parent.parent  # 腳本根目錄
            automation_log_dir = script_root / "output" / "ExecutionResult" / "AutomationLog"
        
        # 確保目錄存在
        try:
            automation_log_dir.mkdir(parents=True, exist_ok=True)
            # 檢查目錄是否可寫
            test_file = automation_log_dir / ".test_write"
            test_file.touch()
            test_file.unlink()
        except Exception as e:
            self.main_logger.warning(f"無法創建或寫入 ExecutionResult/AutomationLog 目錄: {e}，將使用主日誌目錄")
            # 回退到主日誌目錄
            fallback_log_dir = Path(__file__).parent.parent / "logs"
            automation_log_dir = fallback_log_dir
            automation_log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        project_log_file = automation_log_dir / f"{project_name}_automation_log_{timestamp}.txt"

        # 創建專案專用的簡化日誌
        try:
            self.project_log = project_log_file.open('w', encoding='utf-8')
            self.project_log.write(f"專案自動化處理日誌\n")
            self.project_log.write(f"專案: {project_name}\n")
            self.project_log.write(f"開始時間: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.project_log.write("=" * 50 + "\n\n")
            self.project_log.flush()  # 確保實時寫入
            self.main_logger.info(f"專案日誌檔建立: {project_log_file}")
        except Exception as e:
            self.main_logger.error(f"無法建立專案日誌檔: {e}")
            self.project_log = None

        self.main_logger.project_start(project_name)
    
    def log(self, message: str):
        """記錄專案相關訊息"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        if self.project_log:
            try:
                self.project_log.write(f"[{timestamp}] {message}\n")
                self.project_log.flush()
            except Exception as e:
                self.main_logger.error(f"專案日誌寫入失敗: {e}")
        self.main_logger.info(f"[{self.project_name}] {message}")
    
    def success(self):
        """標記專案處理成功"""
        end_time = datetime.now()
        elapsed = (end_time - self.start_time).total_seconds()
        
        if self.project_log:
            try:
                self.project_log.write(f"\n處理完成時間: {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                self.project_log.write(f"總耗時: {elapsed:.2f}秒\n")
                self.project_log.write("狀態: 成功 ✅\n")
                self.project_log.flush()
                self.project_log.close()
            except Exception as e:
                self.main_logger.error(f"專案日誌關閉失敗: {e}")
        
        self.main_logger.project_success(self.project_name, elapsed)
    
    def failed(self, error_msg: str):
        """標記專案處理失敗"""
        end_time = datetime.now()
        elapsed = (end_time - self.start_time).total_seconds()
        
        if self.project_log:
            try:
                self.project_log.write(f"\n處理完成時間: {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                self.project_log.write(f"總耗時: {elapsed:.2f}秒\n")
                self.project_log.write(f"狀態: 失敗 ❌\n")
                self.project_log.write(f"錯誤訊息: {error_msg}\n")
                self.project_log.flush()
                self.project_log.close()
            except Exception as e:
                self.main_logger.error(f"專案日誌關閉失敗: {e}")
        
        self.main_logger.project_failed(self.project_name, error_msg, elapsed)

# 全域日誌記錄器實例
main_logger = AutomationLogger("HybridUIAutomation")

# 便捷函數
def get_logger(name: str = None) -> AutomationLogger:
    """取得日誌記錄器實例"""
    if name:
        return AutomationLogger(name)
    return main_logger

def create_project_logger(project_name: str) -> ProjectLogger:
    """創建專案專用日誌記錄器"""
    return ProjectLogger(project_name, main_logger)