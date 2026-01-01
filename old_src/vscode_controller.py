# -*- coding: utf-8 -*-
"""
Hybrid UI Automation Script - VS Code 操作控制模組
處理開啟專案、關閉專案、記憶清除等 VS Code 操作
"""

import subprocess
import time
import os
import pyautogui
from pathlib import Path
from typing import Optional
import sys

# 導入配置和日誌
sys.path.append(str(Path(__file__).parent.parent))
try:
    from config.config import config
    from src.logger import get_logger
except ImportError:
    try:
        from config import config
        from logger import get_logger
    except ImportError:
        import sys
        sys.path.append(str(Path(__file__).parent.parent / "config"))
        import config
        from logger import get_logger

class VSCodeController:
    """VS Code 操作控制器 - 簡化版本"""
    
    def __init__(self):
        """初始化 VS Code 控制器"""
        self.logger = get_logger("VSCodeController")
        self.current_project_path = None
        self.logger.info("VS Code 控制器初始化完成")
    
    def open_project(self, project_path: str, wait_for_load: bool = True) -> bool:
        """
        開啟專案
        
        Args:
            project_path: 專案路徑
            wait_for_load: 是否等待載入完成
            
        Returns:
            bool: 開啟是否成功
        """
        try:
            project_path = Path(project_path)
            
            if not project_path.exists():
                self.logger.error(f"專案路徑不存在: {project_path}")
                return False
            
            self.logger.info(f"開啟專案: {project_path}")
            
            # 使用命令列開啟專案
            cmd = [
                config.VSCODE_EXECUTABLE, 
                str(project_path),
                "--disable-gpu-sandbox",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
            
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            self.current_project_path = str(project_path)
            
            if wait_for_load:
                self.logger.info(f"等待 VS Code 載入 ({config.VSCODE_STARTUP_DELAY}秒)...")
                time.sleep(config.VSCODE_STARTUP_DELAY)
                
                # 最大化視窗
                self.logger.info("最大化視窗...")
                pyautogui.keyDown('win')
                pyautogui.press('up')
                pyautogui.keyUp('win')
                time.sleep(0.5)
            
            self.logger.info(f"✅ 專案開啟成功: {project_path.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"開啟專案失敗: {str(e)}")
            return False
    
    def close_current_project(self) -> bool:
        """
        關閉當前專案視窗（使用 Alt+F4）
        
        Returns:
            bool: 關閉是否成功
        """
        try:
            self.logger.info("關閉當前專案視窗...")
            
            # 使用 Alt+F4 關閉當前視窗
            pyautogui.hotkey('alt', 'f4')
            time.sleep(1)
            
            self.current_project_path = None
            self.logger.info("✅ 當前專案視窗關閉")
            return True
                
        except Exception as e:
            self.logger.error(f"關閉當前專案時發生錯誤: {str(e)}")
            return False
    
    def get_current_project_info(self) -> Optional[dict]:
        """
        取得當前專案資訊
        
        Returns:
            Optional[dict]: 專案資訊字典
        """
        if not self.current_project_path:
            return None
        
        project_path = Path(self.current_project_path)
        return {
            "name": project_path.name,
            "path": str(project_path),
            "exists": project_path.exists()
        }
    
    def clear_copilot_memory(self, modification_action: str = "keep") -> bool:
        """
        清除 Copilot Chat 記憶
        
        Args:
            modification_action: 當檢測到修改保存提示時的行為 - "keep"(保留) 或 "revert"(復原)
        
        Returns:
            bool: 清除是否成功
        """
        try:
            self.logger.info("開始清除 Copilot Chat 記憶...")
            self.logger.info(f"修改結果處理模式: {modification_action}")
            
            # 導入圖像識別模組
            from src.image_recognition import check_newchat_save_dialog, handle_newchat_save_dialog
            
            # 清除 Copilot 記憶的命令序列
            # 1. 開啟 Copilot Chat (Ctrl+F1)
            pyautogui.hotkey('ctrl', 'f1')
            self.logger.debug("執行快捷鍵: Ctrl+F1 (開啟 Copilot Chat)")
            time.sleep(2)
            
            # 2. 清除對話歷史 (Ctrl+L)
            pyautogui.hotkey('ctrl', 'l')
            self.logger.debug("執行快捷鍵: Ctrl+L (清除對話歷史)")
            time.sleep(1)
            
            # 檢查是否出現保存對話提示
            self.logger.info("檢查是否出現保存對話提示...")
            
            if check_newchat_save_dialog(timeout=2):
                action_desc = "保留修改" if modification_action == "keep" else "復原修改"
                self.logger.info(f"檢測到保存對話提示，執行 {action_desc} 操作")
                
                if handle_newchat_save_dialog(modification_action):
                    self.logger.info(f"✅ 成功處理保存對話提示，已{action_desc}")
                else:
                    self.logger.warning("⚠️ 處理保存對話提示時發生問題")
            else:
                self.logger.debug("未檢測到保存對話提示")
            
            # 3. 關閉 Copilot Chat (Escape)
            pyautogui.press('escape')
            self.logger.debug("按下按鍵: Escape (關閉 Copilot Chat)")
            time.sleep(0.5)
            
            self.logger.info("✅ Copilot Chat 記憶清除完成")
            return True
            
        except Exception as e:
            self.logger.error(f"清除 Copilot Chat 記憶時發生錯誤: {str(e)}")
            return False

# 創建全域實例
vscode_controller = VSCodeController()

# 便捷函數
def open_project(project_path: str, wait_for_load: bool = True) -> bool:
    """開啟專案"""
    return vscode_controller.open_project(project_path, wait_for_load)

def close_current_project() -> bool:
    """關閉當前專案"""
    return vscode_controller.close_current_project()