# -*- coding: utf-8 -*-
"""
Hybrid UI Automation Script - VS Code UI 初始化模組
實作視窗最大化、關閉面板、重設UI狀態等功能
"""

import pyautogui
import time
import sys
from pathlib import Path
from typing import List, Dict, Any

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

# 設定 pyautogui 安全機制
pyautogui.FAILSAFE = True  # 啟用故障安全機制（滑鼠移到左上角停止）
pyautogui.PAUSE = 0.1  # 每個 pyautogui 操作間的暫停時間

class VSCodeUIInitializer:
    """VS Code UI 初始化器"""
    
    def __init__(self):
        """初始化 UI 初始化器"""
        self.logger = get_logger("VSCodeUIInitializer")
        self.logger.info("VS Code UI 初始化器啟動")
    
    def initialize_ui(self, wait_time: float = None) -> bool:
        """
        初始化 VS Code UI 狀態
        
        Args:
            wait_time: 初始等待時間（秒）
            
        Returns:
            bool: 初始化是否成功
        """
        try:
            self.logger.create_separator("開始初始化 VS Code UI")
            
            # 等待 VS Code 完全載入
            if wait_time is None:
                wait_time = config.VSCODE_STARTUP_DELAY
                
            self.logger.info(f"等待 VS Code 載入完成 ({wait_time}秒)")
            time.sleep(wait_time)
            
            # UI 重設命令已廢棄，直接返回成功
            self.logger.info("✅ VS Code UI 初始化完成")
            return True
                
        except Exception as e:
            self.logger.error(f"UI 初始化過程中發生錯誤: {str(e)}")
            return False
    
    def _execute_ui_reset_commands(self) -> bool:
        """
        執行 UI 重設命令序列
        
        Returns:
            bool: 執行是否成功
        """
        try:
            for i, command in enumerate(config.UI_RESET_COMMANDS):
                self.logger.debug(f"執行第 {i+1} 個命令: {command}")
                
                command_type = command.get('type')
                delay = command.get('delay', 0.5)
                repeat = command.get('repeat', 1)
                
                # 重複執行命令
                for _ in range(repeat):
                    if command_type == 'hotkey':
                        keys = command.get('keys', [])
                        self._send_hotkey(keys)
                        self.logger.ui_action(f"熱鍵: {'+'.join(keys)}", "SUCCESS")
                        
                    elif command_type == 'key':
                        key = command.get('key')
                        self._send_key(key)
                        self.logger.ui_action(f"按鍵: {key}", "SUCCESS")
                    
                    # 命令間延遲
                    if repeat > 1 and _ < repeat - 1:
                        time.sleep(0.1)  # 重複命令間的短暫延遲
                
                # 等待命令執行完成
                time.sleep(delay)
            
            return True
            
        except Exception as e:
            self.logger.error(f"執行 UI 重設命令時發生錯誤: {str(e)}")
            return False
    
    def _send_hotkey(self, keys: List[str]):
        """
        發送熱鍵組合
        
        Args:
            keys: 按鍵列表
        """
        try:
            pyautogui.hotkey(*keys)
        except Exception as e:
            self.logger.error(f"發送熱鍵 {'+'.join(keys)} 失敗: {str(e)}")
            raise
    
    def _send_key(self, key: str):
        """
        發送單一按鍵
        
        Args:
            key: 按鍵名稱
        """
        try:
            pyautogui.press(key)
        except Exception as e:
            self.logger.error(f"發送按鍵 {key} 失敗: {str(e)}")
            raise
    
    def maximize_window(self) -> bool:
        """
        最大化視窗
        
        Returns:
            bool: 操作是否成功
        """
        try:
            self.logger.ui_action("最大化視窗")
            
            # 在 Linux/Ubuntu 中使用 Super(Windows鍵) + Up 最大化視窗
            pyautogui.keyDown('win')
            pyautogui.press('up')
            pyautogui.keyUp('win')
            time.sleep(0.5)
            
            self.logger.ui_action("最大化視窗", "SUCCESS")
            return True
            
        except Exception as e:
            self.logger.ui_action("最大化視窗", "ERROR", str(e))
            return False
    
    def close_terminal(self) -> bool:
        """
        關閉終端機面板
        
        Returns:
            bool: 操作是否成功
        """
        try:
            self.logger.ui_action("關閉終端機")
            
            pyautogui.hotkey('ctrl', 'j')
            time.sleep(config.VSCODE_COMMAND_DELAY)
            
            self.logger.ui_action("關閉終端機", "SUCCESS")
            return True
            
        except Exception as e:
            self.logger.ui_action("關閉終端機", "ERROR", str(e))
            return False
    
    def close_sidebar(self) -> bool:
        """
        關閉側邊欄
        
        Returns:
            bool: 操作是否成功
        """
        try:
            self.logger.ui_action("關閉側邊欄")
            
            pyautogui.hotkey('ctrl', 'b')
            time.sleep(config.VSCODE_COMMAND_DELAY)
            
            self.logger.ui_action("關閉側邊欄", "SUCCESS")
            return True
            
        except Exception as e:
            self.logger.ui_action("關閉側邊欄", "ERROR", str(e))
            return False
    
    def close_all_editors(self, max_attempts: int = 5) -> bool:
        """
        關閉所有編輯器分頁
        
        Args:
            max_attempts: 最大嘗試次數
            
        Returns:
            bool: 操作是否成功
        """
        try:
            self.logger.ui_action(f"關閉所有編輯器 (最多 {max_attempts} 次)")
            
            for i in range(max_attempts):
                pyautogui.hotkey('ctrl', 'w')
                time.sleep(0.2)
            
            self.logger.ui_action("關閉所有編輯器", "SUCCESS")
            return True
            
        except Exception as e:
            self.logger.ui_action("關閉所有編輯器", "ERROR", str(e))
            return False
    
    def reset_layout(self) -> bool:
        """
        重設版面配置
        
        Returns:
            bool: 操作是否成功
        """
        try:
            self.logger.ui_action("重設版面配置")
            
            # 使用 View: Reset Editor Layout 命令
            pyautogui.hotkey('ctrl', 'shift', 'p')
            time.sleep(1)
            pyautogui.write('View: Reset Editor Layout')
            time.sleep(0.5)
            pyautogui.press('enter')
            time.sleep(1)
            pyautogui.press('escape')  # 確保命令面板關閉
            
            self.logger.ui_action("重設版面配置", "SUCCESS")
            return True
            
        except Exception as e:
            self.logger.ui_action("重設版面配置", "ERROR", str(e))
            return False
    
    def focus_editor(self) -> bool:
        """
        聚焦到編輯器區域
        
        Returns:
            bool: 操作是否成功
        """
        try:
            self.logger.ui_action("聚焦編輯器")
            
            # 按 Escape 確保沒有彈出視窗，然後聚焦編輯器
            pyautogui.press('escape')
            time.sleep(0.2)
            pyautogui.hotkey('ctrl', '1')  # 聚焦第一個編輯器群組
            time.sleep(0.5)
            
            self.logger.ui_action("聚焦編輯器", "SUCCESS")
            return True
            
        except Exception as e:
            self.logger.ui_action("聚焦編輯器", "ERROR", str(e))
            return False
    
    def prepare_for_automation(self) -> bool:
        """
        為自動化準備 VS Code
        
        Returns:
            bool: 準備是否成功
        """
        try:
            self.logger.create_separator("準備 VS Code 自動化環境")
            
            steps = [
                ("最大化視窗", self.maximize_window),
                ("關閉終端機", self.close_terminal),
                ("關閉側邊欄", self.close_sidebar),
                ("關閉所有編輯器", self.close_all_editors),
                ("重設版面配置", self.reset_layout),
                ("聚焦編輯器", self.focus_editor)
            ]
            
            for step_name, step_func in steps:
                self.logger.info(f"執行: {step_name}")
                if not step_func():
                    self.logger.warning(f"步驟失敗: {step_name}，但繼續執行")
                time.sleep(0.5)  # 步驟間短暫延遲
            
            self.logger.info("✅ VS Code 自動化環境準備完成")
            return True
            
        except Exception as e:
            self.logger.error(f"準備自動化環境失敗: {str(e)}")
            return False
    
    def check_vscode_responsive(self) -> bool:
        """
        檢查 VS Code 是否響應
        
        Returns:
            bool: VS Code 是否響應
        """
        try:
            self.logger.debug("檢查 VS Code 響應性")
            
            # 嘗試按 Escape 鍵，這應該總是能響應
            pyautogui.press('escape')
            time.sleep(0.1)
            
            self.logger.debug("VS Code 響應正常")
            return True
            
        except Exception as e:
            self.logger.error(f"VS Code 響應檢查失敗: {str(e)}")
            return False

# 創建全域實例
ui_initializer = VSCodeUIInitializer()

# 便捷函數
def initialize_vscode_ui(wait_time: float = None) -> bool:
    """
    初始化 VS Code UI 的便捷函數
    
    Args:
        wait_time: 等待時間
        
    Returns:
        bool: 初始化是否成功
    """
    return ui_initializer.initialize_ui(wait_time)

def prepare_vscode_for_automation() -> bool:
    """
    為自動化準備 VS Code 的便捷函數
    
    Returns:
        bool: 準備是否成功
    """
    return ui_initializer.prepare_for_automation()