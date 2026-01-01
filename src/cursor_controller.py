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
    from src.cursor_ui_initializer import initialize_cursor_ui
except ImportError:
    try:
        from config import config
        from logger import get_logger
        from cursor_ui_initializer import initialize_cursor_ui
    except ImportError:
        import sys
        sys.path.append(str(Path(__file__).parent.parent / "config"))
        import config
        from logger import get_logger
        from cursor_ui_initializer import initialize_cursor_ui

class CursorController:
    """Cursor 操作控制器"""
    
    def __init__(self):
        """初始化 Cursor 控制器"""
        self.logger = get_logger("CursorController")
        self.current_project_path = None
        self.logger.info("Cursor 控制器初始化完成")
    
    
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
            self.logger.info(f"開啟專案: {project_path.name}")
            
            # 設置環境變量以提高穩定性
            env = os.environ.copy()
            env['ELECTRON_DISABLE_SECURITY_WARNINGS'] = '1'
            env['ELECTRON_NO_ATTACH_CONSOLE'] = '1'
            
            # 使用命令列開啟專案
            cmd = [config.VSCODE_EXECUTABLE, str(project_path)]
            self.logger.debug(f"執行命令: {' '.join(cmd)}")
            
            # 直接啟動 Cursor
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(project_path.parent),
                env=env
            )
            
            self.logger.info("🎯 專案進程已啟動")
            self.current_project_path = str(project_path)
            
            if wait_for_load:
                # 等待 Cursor 啟動
                self.logger.info("等待 Cursor 啟動...")
                time.sleep(config.VSCODE_STARTUP_DELAY)
                
                # 最大化視窗
                self.logger.info("正在最大化視窗...")
                self._maximize_window_direct()
                
                return True
            else:
                return True
                
        except Exception as e:
            self.logger.error(f"啟動 Cursor 過程中發生錯誤: {str(e)}")
            return False
    
    def close_current_project(self) -> bool:
        """
        關閉當前專案（使用 Ctrl+Shift+W 快捷鍵）
            
        Returns:
            bool: 關閉是否成功
        """
        try:
            if not self.current_project_path:
                self.logger.debug("沒有開啟的專案需要關閉")
                return True
            
            self.logger.info(f"關閉專案: {Path(self.current_project_path).name}")
            self.logger.info("🎯 使用 Ctrl+Shift+W 關閉 Cursor 視窗...")
            
            # 發送 Ctrl+Shift+W 快捷鍵關閉當前視窗
            pyautogui.hotkey('ctrl', 'shift', 'w')
            
            # 等待一小段時間讓關閉操作生效
            time.sleep(2)
            
            self.logger.info("✅ 已發送關閉視窗快捷鍵")
            
            # 清理狀態
            self.current_project_path = None
            
            return True
                    
        except Exception as e:
            self.logger.error(f"關閉專案時發生錯誤: {str(e)}")
            return False
    
    def ensure_clean_environment(self) -> bool:
        """
        確保乾淨的執行環境（關閉所有 VS Code 實例）
        
        Returns:
            bool: 清理是否成功
        """
        try:
            self.logger.info("確保乾淨的執行環境...")
            
            # 使用簡單的快捷鍵關閉所有 Cursor 視窗
            # 發送多次 Ctrl+Shift+W 確保關閉所有視窗
            for i in range(3):
                try:
                    pyautogui.hotkey('ctrl', 'shift', 'w')
                    time.sleep(1)
                    self.logger.debug(f"發送關閉快捷鍵 ({i+1}/3)")
                except Exception as e:
                    self.logger.debug(f"發送快捷鍵失敗: {e}")
            
            time.sleep(2)  # 等待關閉操作完成
            self.logger.info("✅ 環境清理完成")
            
            # 清理狀態
            self.current_project_path = None
            
            return True
                
        except Exception as e:
            self.logger.error(f"清理環境時發生錯誤: {str(e)}")
            return False
    
    def _maximize_window_direct(self) -> bool:
        """
        直接最大化視窗，不影響既有畫面
        
        Returns:
            bool: 操作是否成功
        """
        try:
            self.logger.info("正在最大化 VS Code 視窗...")
            
            # 使用 Super+Up 快捷鍵最大化視窗
            pyautogui.keyDown('win')
            pyautogui.press('up')
            pyautogui.keyUp('win')
            time.sleep(0.5)
            
            self.logger.info("✅ 視窗最大化完成")
            return True
            
        except Exception as e:
            self.logger.error(f"最大化視窗失敗: {str(e)}")
            return False

    def restart_vscode(self, project_path: str = None) -> bool:
        """
        重啟 VS Code
        
        Args:
            project_path: 要重新開啟的專案路徑
            
        Returns:
            bool: 重啟是否成功
        """
        try:
            self.logger.info("重啟 VS Code...")
            
            # 關閉所有實例
            self.logger.info("使用快捷鍵關閉所有 Cursor 實例...")
            self.ensure_clean_environment()
            
            # 等待完全關閉
            time.sleep(3)
            
            # 如果指定了專案路徑，重新開啟
            if project_path:
                return self.open_project(project_path)
            else:
                self.logger.info("✅ VS Code 重啟完成（未開啟專案）")
                return True
                
        except Exception as e:
            self.logger.error(f"重啟 VS Code 時發生錯誤: {str(e)}")
            return False
    
    def wait_for_vscode_ready(self, timeout: int = 30) -> bool:
        """
        等待 VS Code 準備就緒
        
        Args:
            timeout: 超時時間（秒）
            
        Returns:
            bool: VS Code 是否準備就緒
        """
        try:
            self.logger.debug(f"等待 VS Code 準備就緒 (超時: {timeout}秒)")
            
            start_time = time.time()
            
            # 簡單等待指定時間
            time.sleep(min(timeout, 10))  # 最多等待10秒
            self.logger.debug("VS Code 等待完成")
            
            self.logger.warning(f"VS Code 在 {timeout} 秒內未準備就緒")
            return False
            
        except Exception as e:
            self.logger.error(f"等待 VS Code 準備就緒時發生錯誤: {str(e)}")
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
    
    def save_all_files(self) -> bool:
        """
        儲存所有檔案
        
        Returns:
            bool: 儲存是否成功
        """
        try:
            self.logger.debug("儲存所有檔案...")
            
            pyautogui.hotkey('ctrl', 'shift', 's')  # Ctrl+Shift+S 儲存全部
            time.sleep(1)
            
            self.logger.debug("所有檔案已儲存")
            return True
            
        except Exception as e:
            self.logger.error(f"儲存檔案時發生錯誤: {str(e)}")
            return False
    
    def focus_vscode_window(self) -> bool:
        """
        聚焦 VS Code 視窗
        
        Returns:
            bool: 聚焦是否成功
        """
        try:
            # 嘗試使用 Alt+Tab 切換到 VS Code
            pyautogui.hotkey('alt', 'tab')
            time.sleep(0.5)
            
            # 不再點擊螢幕中央，避免不必要的滑鼠操作
            # 改用鍵盤確保聚焦
            pyautogui.press('ctrl')  # 簡單的鍵盤操作確保視窗聚焦
            time.sleep(0.5)
            
            self.logger.debug("VS Code 視窗已聚焦")
            return True
            
        except Exception as e:
            self.logger.error(f"聚焦 VS Code 視窗時發生錯誤: {str(e)}")
            return False
    
    def clear_copilot_memory(self, modification_action: str = "keep") -> bool:
        """
        清除 Copilot Chat 記憶，包含智能檢測和處理保存對話提示
        
        Args:
            modification_action: 當檢測到修改保存提示時的行為 - "keep"(保留) 或 "revert"(復原)
        
        Returns:
            bool: 清除是否成功
        """
        try:
            self.logger.info("開始清除 Copilot Chat 記憶...")
            self.logger.info(f"修改結果處理模式: {modification_action}")
            
            # 導入圖像識別模組
            from src.image_recognition import handle_save_dialog_with_image_recognition
            
            # 步驟1: 在執行 Ctrl+T 之前，先檢測並處理保存對話框
            self.logger.info("在執行清除命令前，先檢測保存對話框...")
            
            # 使用新的圖像辨識方法處理保存對話框
            dialog_handled = handle_save_dialog_with_image_recognition(modification_action)
            
            if dialog_handled:
                self.logger.info("保存對話框處理完成，繼續執行清除命令...")
            else:
                self.logger.info("未檢測到保存對話框或處理失敗，繼續執行清除命令...")
            
            # 步驟2: 執行清除記憶命令序列
            self.logger.info("執行 Copilot Chat 清除命令序列...")
            
            for i, command in enumerate(config.COPILOT_CLEAR_MEMORY_COMMANDS):
                if command['type'] == 'hotkey':
                    pyautogui.hotkey(*command['keys'])
                    self.logger.debug(f"執行快捷鍵: {'+'.join(command['keys'])}")
                elif command['type'] == 'key':
                    pyautogui.press(command['key'])
                    self.logger.debug(f"按下按鍵: {command['key']}")
                
                time.sleep(command['delay'])
            
            self.logger.info("✅ Copilot Chat 記憶清除流程完成")
            return True
            
        except Exception as e:
            self.logger.error(f"清除 Copilot Chat 記憶時發生錯誤: {str(e)}")
            return False

# 創建全域實例
cursor_controller = CursorController()

# 便捷函數
def open_project(project_path: str, wait_for_load: bool = True) -> bool:
    """開啟專案的便捷函數"""
    return cursor_controller.open_project(project_path, wait_for_load)

def close_current_project() -> bool:
    """關閉當前專案的便捷函數"""
    return cursor_controller.close_current_project()

def ensure_clean_environment() -> bool:
    """確保乾淨環境的便捷函數"""
    return cursor_controller.ensure_clean_environment()

def restart_vscode(project_path: str = None) -> bool:
    """重啟 VS Code 的便捷函數"""
    return cursor_controller.restart_vscode(project_path)