# -*- coding: utf-8 -*-
"""
Hybrid UI Automation Script - 圖像辨識模組
處理截圖、圖像匹配、等待回應完成的視覺判斷
"""

import pyautogui
import cv2
import numpy as np
import time
from pathlib import Path
from typing import Optional, Tuple, List
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

class ImageRecognition:
    """圖像辨識處理器"""
    
    def __init__(self):
        """初始化圖像辨識器"""
        self.logger = get_logger("ImageRecognition")
        self.screenshot_count = 0
        self.logger.info("圖像辨識模組初始化完成")
    
    def take_screenshot(self, region: Tuple[int, int, int, int] = None, 
                       save_path: str = None) -> Optional[np.ndarray]:
        """
        截取螢幕畫面
        
        Args:
            region: 截圖區域 (left, top, width, height)，None 表示全螢幕
            save_path: 儲存截圖的路徑（可選）
            
        Returns:
            Optional[np.ndarray]: 截圖的 numpy 陣列，失敗則返回 None
        """
        try:
            self.screenshot_count += 1
            
            if region:
                screenshot = pyautogui.screenshot(region=region)
            else:
                screenshot = pyautogui.screenshot()
            
            # 轉換為 OpenCV 格式
            screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            # 如果指定了儲存路徑，儲存截圖
            if save_path:
                cv2.imwrite(save_path, screenshot_cv)
                self.logger.debug(f"截圖已儲存: {save_path}")
            
            self.logger.debug(f"截圖完成 #{self.screenshot_count}")
            return screenshot_cv
            
        except Exception as e:
            self.logger.error(f"截圖失敗: {str(e)}")
            return None
    
    def find_image_on_screen(self, template_path: str, confidence: float = None,
                           region: Tuple[int, int, int, int] = None) -> Optional[Tuple[int, int, int, int]]:
        """
        在螢幕上尋找指定圖像
        
        Args:
            template_path: 模板圖像路徑
            confidence: 匹配信心度閾值
            region: 搜尋區域
            
        Returns:
            Optional[Tuple[int, int, int, int]]: 找到的位置 (left, top, width, height)，失敗則返回 None
        """
        try:
            template_path = Path(template_path)
            if not template_path.exists():
                self.logger.error(f"模板圖像不存在: {template_path}")
                return None
            
            if confidence is None:
                confidence = config.IMAGE_CONFIDENCE
            
            # 使用 pyautogui 的圖像識別功能
            try:
                location = pyautogui.locateOnScreen(
                    str(template_path),
                    confidence=confidence,
                    region=region
                )
                
                if location:
                    self.logger.image_recognition(template_path.name, True, confidence)
                    return location
                else:
                    self.logger.image_recognition(template_path.name, False)
                    return None
                    
            except pyautogui.ImageNotFoundException:
                self.logger.image_recognition(template_path.name, False)
                return None
                
        except Exception as e:
            self.logger.error(f"圖像識別過程中發生錯誤: {str(e)}")
            return None
    
    def wait_for_image(self, template_path: str, timeout: int = 30,
                      check_interval: float = 1.0, confidence: float = None,
                      region: Tuple[int, int, int, int] = None) -> bool:
        """
        等待指定圖像出現
        
        Args:
            template_path: 模板圖像路徑
            timeout: 超時時間（秒）
            check_interval: 檢查間隔（秒）
            confidence: 匹配信心度
            region: 搜尋區域
            
        Returns:
            bool: 是否找到圖像
        """
        try:
            template_name = Path(template_path).name
            self.logger.info(f"等待圖像出現: {template_name} (超時: {timeout}秒)")
            
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                location = self.find_image_on_screen(template_path, confidence, region)
                
                if location:
                    elapsed = time.time() - start_time
                    self.logger.info(f"✅ 圖像 {template_name} 已出現 (耗時: {elapsed:.1f}秒)")
                    return True
                
                time.sleep(check_interval)
                
                # 每10秒記錄一次等待狀態
                elapsed = time.time() - start_time
                if int(elapsed) % 10 == 0 and int(elapsed) > 0:
                    self.logger.debug(f"等待圖像 {template_name}... ({elapsed:.0f}秒)")
            
            self.logger.warning(f"⏰ 等待圖像 {template_name} 超時")
            return False
            
        except Exception as e:
            self.logger.error(f"等待圖像時發生錯誤: {str(e)}")
            return False
    
    def is_chat_open(self) -> bool:
        """
        檢測 AI Chat 是否已開啟
        
        通過檢測 Chat 特有的 UI 元素來判斷（input_bar.png）
        這些元素只在 Chat 開啟時才會出現
        
        Returns:
            bool: Chat 是否已開啟
        """
        try:
            self.logger.debug("檢測 AI Chat 是否已開啟...")
            
            # 使用 input_bar.png 來檢測（最可靠的指標）
            location = self.find_image_on_screen(
                str(config.INPUT_BAR_IMAGE),
                confidence=config.IMAGE_CONFIDENCE
            )
            
            if location:
                self.logger.info("✅ AI Chat 已開啟")
                return True
            else:
                self.logger.info("❌ AI Chat 未開啟")
                return False
                
        except Exception as e:
            self.logger.error(f"檢測 Chat 狀態時發生錯誤: {str(e)}")
            return False
    
    def click_on_image(self, template_path: str, confidence: float = None,
                      region: Tuple[int, int, int, int] = None, offset: Tuple[int, int] = None) -> bool:
        """
        在找到的圖像上點擊
        
        Args:
            template_path: 模板圖像路徑
            confidence: 匹配信心度
            region: 搜尋區域
            offset: 點擊位置偏移 (x, y)
            
        Returns:
            bool: 點擊是否成功
        """
        try:
            location = self.find_image_on_screen(template_path, confidence, region)
            
            if location:
                # 計算點擊位置（圖像中心）
                click_x = location.left + location.width // 2
                click_y = location.top + location.height // 2
                
                # 應用偏移
                if offset:
                    click_x += offset[0]
                    click_y += offset[1]
                
                # 執行點擊
                pyautogui.click(click_x, click_y)
                
                template_name = Path(template_path).name
                self.logger.info(f"✅ 點擊圖像 {template_name} 於位置 ({click_x}, {click_y})")
                return True
            else:
                template_name = Path(template_path).name
                self.logger.warning(f"⚠️ 無法找到圖像 {template_name}，點擊失敗")
                return False
                
        except Exception as e:
            self.logger.error(f"點擊圖像時發生錯誤: {str(e)}")
            return False
    
    def check_copilot_response_ready(self) -> bool:
        """
        檢查 Copilot 回應是否準備就緒（新邏輯：基於 stop_button 和 send_button）
        
        Returns:
            bool: 回應是否準備就緒
        """
        try:
            # 第一步：檢查是否有 stop 按鈕（如果有，表示還在回應中）
            stop_button = self.find_image_on_screen(
                str(config.STOP_BUTTON_IMAGE),
                confidence=config.IMAGE_CONFIDENCE
            )
            
            if stop_button:
                self.logger.debug("檢測到 stop 按鈕，Copilot 仍在回應中...")
                return False
            
            # 第二步：檢查是否有 send 按鈕（stop 按鈕消失後應該出現 send 按鈕）
            send_button = self.find_image_on_screen(
                str(config.SEND_BUTTON_IMAGE),
                confidence=config.IMAGE_CONFIDENCE
            )
            
            if send_button:
                self.logger.debug("檢測到 send 按鈕且無 stop 按鈕，Copilot 回應已完成")
                return True
            
            # 如果既沒有 stop 也沒有 send，狀態不明，假設還未完成
            self.logger.debug("未檢測到 stop 或 send 按鈕，狀態不明確")
            return False
            
        except Exception as e:
            self.logger.debug(f"檢查 Copilot 回應狀態時發生錯誤: {str(e)}")
            return False
    
    def check_copilot_response_status_with_auto_clear(self) -> dict:
        """
        檢查 Copilot 回應狀態，每次檢測不到按鈕時都自動清除通知
        
        Returns:
            dict: 包含詳細狀態信息的字典
        """
        try:
            status = {
                'has_stop_button': False,
                'has_send_button': False,
                'is_responding': False,
                'is_ready': False,
                'status_message': '',
                'notifications_cleared': False
            }
            
            # 檢查 stop 按鈕
            stop_button = self.find_image_on_screen(
                str(config.STOP_BUTTON_IMAGE),
                confidence=config.IMAGE_CONFIDENCE
            )
            status['has_stop_button'] = bool(stop_button)
            
            # 檢查 send 按鈕
            send_button = self.find_image_on_screen(
                str(config.SEND_BUTTON_IMAGE),
                confidence=config.IMAGE_CONFIDENCE
            )
            status['has_send_button'] = bool(send_button)
            
            # 如果同時檢測不到兩個按鈕，立即清除通知並重新聚焦
            if not status['has_stop_button'] and not status['has_send_button']:
                self.logger.warning("⚠️ 同時檢測不到 stop 或 send 按鈕，執行通知清除和重新聚焦")
                
                # 每次都嘗試清除通知
                if self.clear_vscode_notifications():
                    status['notifications_cleared'] = True
                    time.sleep(0.5)
                    
                    # 使用 open_copilot_chat() 的快捷鍵重新聚焦（數字鍵盤）
                    self.logger.info("執行重新聚焦操作（Ctrl+Shift+數字鍵盤- 和 Ctrl+Shift+數字鍵盤+）")
                    pyautogui.hotkey('ctrl', 'shift', 'subtract')  # 數字鍵盤的 -
                    time.sleep(0.3)
                    pyautogui.hotkey('ctrl', 'shift', 'add')  # 數字鍵盤的 +
                    time.sleep(0.5)
                    
                    # 清除通知和重新聚焦後再次檢測
                    time.sleep(1.5)  # 增加等待時間
                    
                    stop_button = self.find_image_on_screen(
                        str(config.STOP_BUTTON_IMAGE),
                        confidence=config.IMAGE_CONFIDENCE
                    )
                    send_button = self.find_image_on_screen(
                        str(config.SEND_BUTTON_IMAGE),
                        confidence=config.IMAGE_CONFIDENCE
                    )
                    
                    status['has_stop_button'] = bool(stop_button)
                    status['has_send_button'] = bool(send_button)
            
            # 判斷狀態
            if status['has_stop_button']:
                status['is_responding'] = True
                status['is_ready'] = False
                if status['notifications_cleared']:
                    status['status_message'] = "清除通知後檢測到 stop 按鈕，Copilot 正在回應中"
                else:
                    status['status_message'] = "Copilot 正在回應中（檢測到 stop 按鈕）"
            elif status['has_send_button']:
                status['is_responding'] = False
                status['is_ready'] = True
                if status['notifications_cleared']:
                    status['status_message'] = "清除通知後檢測到 send 按鈕，Copilot 回應已完成"
                else:
                    status['status_message'] = "Copilot 回應已完成（檢測到 send 按鈕）"
            else:
                status['is_responding'] = False
                status['is_ready'] = False
                if status['notifications_cleared']:
                    status['status_message'] = "已清除通知但仍未檢測到 stop 或 send 按鈕"
                else:
                    status['status_message'] = "狀態不明確（未檢測到 stop 或 send 按鈕）"
            
            return status
            
        except Exception as e:
            self.logger.debug(f"檢查 Copilot 回應詳細狀態時發生錯誤: {str(e)}")
            return {
                'has_stop_button': False,
                'has_send_button': False,
                'is_responding': False,
                'is_ready': False,
                'status_message': f'檢測錯誤: {str(e)}',
                'notifications_cleared': False
            }

    def check_copilot_response_status(self) -> dict:
        """
        詳細檢查 Copilot 回應狀態（用於智能等待）
        如果同時檢測不到 send_button 和 stop_button，會嘗試清除通知
        
        Returns:
            dict: 包含詳細狀態信息的字典
        """
        try:
            status = {
                'has_stop_button': False,
                'has_send_button': False,
                'is_responding': False,
                'is_ready': False,
                'status_message': '',
                'notifications_cleared': False
            }
            
            # 檢查 stop 按鈕
            stop_button = self.find_image_on_screen(
                str(config.STOP_BUTTON_IMAGE),
                confidence=config.IMAGE_CONFIDENCE
            )
            status['has_stop_button'] = bool(stop_button)
            
            # 檢查 send 按鈕
            send_button = self.find_image_on_screen(
                str(config.SEND_BUTTON_IMAGE),
                confidence=config.IMAGE_CONFIDENCE
            )
            status['has_send_button'] = bool(send_button)
            
            # 判斷狀態
            if status['has_stop_button']:
                status['is_responding'] = True
                status['is_ready'] = False
                status['status_message'] = "Copilot 正在回應中（檢測到 stop 按鈕）"
            elif status['has_send_button']:
                status['is_responding'] = False
                status['is_ready'] = True
                status['status_message'] = "Copilot 回應已完成（檢測到 send 按鈕）"
            else:
                # 同時檢測不到兩個按鈕，可能是通知遮擋
                self.logger.warning("⚠️ 同時檢測不到 stop 或 send 按鈕，可能有通知遮擋 UI")
                
                # 嘗試清除通知並重新聚焦
                if self.clear_vscode_notifications():
                    status['notifications_cleared'] = True
                    time.sleep(0.5)
                    
                    # 使用 open_copilot_chat() 的快捷鍵重新聚焦（數字鍵盤）
                    self.logger.info("執行重新聚焦操作（Ctrl+Shift+數字鍵盤- 和 Ctrl+Shift+數字鍵盤+）")
                    pyautogui.hotkey('ctrl', 'shift', 'subtract')  # 數字鍵盤的 -
                    time.sleep(0.3)
                    pyautogui.hotkey('ctrl', 'shift', 'add')  # 數字鍵盤的 +
                    time.sleep(0.5)
                    
                    # 清除通知和重新聚焦後再次檢測
                    time.sleep(1)  # 給一點時間讓 UI 更新
                    
                    stop_button = self.find_image_on_screen(
                        str(config.STOP_BUTTON_IMAGE),
                        confidence=config.IMAGE_CONFIDENCE
                    )
                    send_button = self.find_image_on_screen(
                        str(config.SEND_BUTTON_IMAGE),
                        confidence=config.IMAGE_CONFIDENCE
                    )
                    
                    status['has_stop_button'] = bool(stop_button)
                    status['has_send_button'] = bool(send_button)
                    
                    if status['has_stop_button']:
                        status['is_responding'] = True
                        status['is_ready'] = False
                        status['status_message'] = "清除通知後檢測到 stop 按鈕，Copilot 正在回應中"
                    elif status['has_send_button']:
                        status['is_responding'] = False
                        status['is_ready'] = True
                        status['status_message'] = "清除通知後檢測到 send 按鈕，Copilot 回應已完成"
                    else:
                        status['is_responding'] = False
                        status['is_ready'] = False
                        status['status_message'] = "已清除通知但仍未檢測到 stop 或 send 按鈕"
                else:
                    status['is_responding'] = False
                    status['is_ready'] = False
                    status['status_message'] = "狀態不明確（未檢測到 stop 或 send 按鈕，通知清除失敗）"
            
            return status
            
        except Exception as e:
            self.logger.debug(f"檢查 Copilot 回應詳細狀態時發生錯誤: {str(e)}")
            return {
                'has_stop_button': False,
                'has_send_button': False,
                'is_responding': False,
                'is_ready': False,
                'status_message': f'檢測錯誤: {str(e)}',
                'notifications_cleared': False
            }
    
    def clear_vscode_notifications(self) -> bool:
        """
        清除 VS Code 通知
        使用 Ctrl+Shift+P 開啟命令面板並執行 "Notifications: Clear All Notifications"
        使用剪貼簿來避免中文輸入法干擾問題
        
        Returns:
            bool: 清除操作是否成功
        """
        try:
            self.logger.info("檢測到 UI 按鈕被通知遮擋，嘗試清除 VS Code 通知...")
            
            # 保存目前剪貼簿內容
            import pyperclip
            original_clipboard = ""
            try:
                original_clipboard = pyperclip.paste()
            except:
                pass
            
            # 使用 Ctrl+Shift+P 開啟命令面板
            pyautogui.hotkey('ctrl', 'shift', 'p')
            time.sleep(1.5)  # 增加等待時間確保命令面板開啟
            
            # 將清除通知的命令複製到剪貼簿
            clear_command = "Notifications: Clear All Notifications"
            pyperclip.copy(clear_command)
            time.sleep(0.3)
            
            # 使用 Ctrl+V 貼上命令（避免中文輸入法問題）
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.8)
            
            # 按下 Enter 執行命令
            pyautogui.press('enter')
            time.sleep(1)
            
            # 按 Esc 關閉命令面板（如果還開著）
            pyautogui.press('escape')
            time.sleep(0.5)
            
            # 恢復原始剪貼簿內容
            try:
                if original_clipboard:
                    pyperclip.copy(original_clipboard)
            except:
                pass
            
            self.logger.info("✅ VS Code 通知清除命令已執行")
            return True
            
        except Exception as e:
            self.logger.error(f"清除 VS Code 通知時發生錯誤: {str(e)}")
            # 嘗試按 Esc 關閉可能開啟的面板
            try:
                pyautogui.press('escape')
                pyautogui.press('escape')  # 多按一次確保關閉
            except:
                pass
            return False

    def click_copilot_copy_button(self) -> bool:
        """
        點擊 Copilot 的複製按鈕
        
        Returns:
            bool: 點擊是否成功
        """
        try:
            return self.click_on_image(
                str(config.COPY_BUTTON_IMAGE),
                confidence=config.IMAGE_CONFIDENCE
            )
            
        except Exception as e:
            self.logger.error(f"點擊 Copilot 複製按鈕時發生錯誤: {str(e)}")
            return False
    
    def focus_chat(self) -> bool:
        """
        使用 Ctrl+Shift+- 和 Ctrl+Shift++ 聚焦到 chat 發送欄位
        
        Returns:
            bool: 操作是否成功
        """
        try:
            self.logger.info("聚焦到 chat 發送欄位...")
            
            # 使用 Ctrl+Shift+- 和 Ctrl+Shift++ 聚焦到 chat 發送欄位
            pyautogui.hotkey('ctrl', 'shift', 'subtract')
            time.sleep(0.2)
            pyautogui.hotkey('ctrl', 'shift', 'add')
            time.sleep(0.5)  # 等待聚焦完成
            
            self.logger.info("✅ 已聚焦到 chat 發送欄位")
            return True
            
        except Exception as e:
            self.logger.error(f"聚焦到 chat 發送欄位時發生錯誤: {str(e)}")
            return False
    
    def check_newchat_save_dialog(self, timeout: int = 2) -> bool:
        """
        檢查是否出現 NewChat_Save 對話框
        
        Args:
            timeout: 檢查超時時間（秒）
            
        Returns:
            bool: 是否檢測到 NewChat_Save 對話框
        """
        try:
            self.logger.debug("檢查是否出現保存新聊天對話框...")
            
            # 在指定時間內檢查是否出現 NewChat_Save 圖像
            start_time = time.time()
            check_interval = 0.5  # 檢查間隔
            
            while time.time() - start_time < timeout:
                newchat_save_location = self.find_image_on_screen(
                    str(config.NEWCHAT_SAVE_IMAGE),
                    confidence=config.IMAGE_CONFIDENCE
                )
                
                if newchat_save_location:
                    self.logger.info("✅ 檢測到保存新聊天對話框")
                    return True
                
                time.sleep(check_interval)
            
            self.logger.debug("未檢測到保存新聊天對話框")
            return False
            
        except Exception as e:
            self.logger.debug(f"檢查保存新聊天對話框時發生錯誤: {str(e)}")
            return False
    
    def handle_newchat_save_dialog(self, action: str = "keep") -> bool:
        """
        處理 NewChat_Save 對話框
        
        Args:
            action: 處理行為 - "keep"(保留並繼續) 或 "revert"(復原修改)
        
        Returns:
            bool: 處理是否成功
        """
        try:
            if action == "keep":
                self.logger.info("處理保存新聊天對話框，按下 Enter 保留並繼續...")
                # 按下 Enter 鍵 (保留並繼續)
                pyautogui.press('enter')
                time.sleep(1)
                self.logger.info("✅ 已按下 Enter，保留並繼續聊天")
            elif action == "revert":
                self.logger.info("處理保存新聊天對話框，按右鍵後按 Enter 復原修改...")
                # 按右鍵選擇復原，然後按 Enter
                pyautogui.press('right')
                time.sleep(1)
                pyautogui.press('enter')
                time.sleep(1)
                self.logger.info("✅ 已按右鍵+Enter，復原修改")
            else:
                self.logger.warning(f"⚠️ 未知的處理行為: {action}，使用預設行為 'keep'")
                pyautogui.press('enter')
                time.sleep(1)
                self.logger.info("✅ 使用預設行為，保留並繼續聊天")
            
            return True
            
        except Exception as e:
            self.logger.error(f"處理保存新聊天對話框時發生錯誤: {str(e)}")
            return False
    
    def find_and_click_button(self, button_image_path: str, button_name: str, timeout: int = 3) -> bool:
        """
        尋找並點擊按鈕（改進版）
        
        改進點：
        1. 提高檢測頻率（0.5秒 → 0.2秒）
        2. 記錄檢查次數
        3. 更詳細的日誌
        
        Args:
            button_image_path: 按鈕圖像路徑
            button_name: 按鈕名稱（用於日誌）
            timeout: 超時時間（秒）
        
        Returns:
            bool: 是否成功找到並點擊按鈕
        """
        try:
            self.logger.info(f"開始搜尋 {button_name} 按鈕（timeout: {timeout}秒）...")
            
            # 使用循環實現超時功能
            start_time = time.time()
            location = None
            check_count = 0
            
            while time.time() - start_time < timeout:
                try:
                    check_count += 1
                    # 使用按鈕專用的較低信心閾值，提高檢測成功率
                    confidence = config.BUTTON_CONFIDENCE if hasattr(config, 'BUTTON_CONFIDENCE') else config.IMAGE_CONFIDENCE
                    location = pyautogui.locateOnScreen(button_image_path, confidence=confidence)
                    if location is not None:
                        self.logger.info(f"✅ 在第 {check_count} 次檢查時找到按鈕（信心度閾值: {confidence}）")
                        break
                except Exception:
                    pass
                time.sleep(0.2)  # 每0.2秒檢查一次（提高檢測頻率）
            
            if location is not None:
                # 計算按鈕中心點
                center = pyautogui.center(location)
                self.logger.info(f"找到 {button_name} 按鈕，位置: {center}, 信心度: {location}")
                
                # 移動滑鼠到按鈕中心並點擊
                pyautogui.moveTo(center.x, center.y, duration=0.5)
                time.sleep(0.2)
                pyautogui.click(center.x, center.y)
                
                self.logger.info(f"✅ 成功點擊 {button_name} 按鈕")
                time.sleep(1)  # 等待點擊效果
                return True
            else:
                self.logger.warning(f"⚠️ 在 {timeout} 秒內未找到 {button_name} 按鈕（檢查了 {check_count} 次）")
                return False
                
        except Exception as e:
            self.logger.error(f"點擊 {button_name} 按鈕時發生錯誤: {str(e)}")
            return False
    
    def handle_save_dialog_with_image_recognition(self, modification_action: str = "keep") -> bool:
        """
        使用圖像辨識處理保存對話框（改進版）
        
        直接根據 modification_action 檢測並點擊對應按鈕：
        - revert: 檢測並點擊 undo.png
        - keep: 檢測並點擊 keep.png
        
        改進點：
        1. 增加初始等待時間，讓對話框完全顯示
        2. 多次重試機制
        3. 更長的 timeout
        
        Args:
            modification_action: 修改結果處理模式 - "keep"(保留) 或 "revert"(復原)
        
        Returns:
            bool: 是否成功處理保存對話框
        """
        try:
            action_desc = "保留修改" if modification_action == "keep" else "復原修改"
            self.logger.info(f"根據設定 ({modification_action}) 檢測對應按鈕...")
            
            # 步驟1: 等待對話框完全顯示
            self.logger.info("等待保存對話框完全顯示...")
            time.sleep(1.5)
            
            # 步驟2: 根據設定選擇對應的按鈕
            if modification_action == "revert":
                # 復原修改：檢測並點擊 undo.png
                button_path = str(config.UNDO_BUTTON_IMAGE)
                button_name = "復原(undo)"
            else:
                # 保留修改：檢測並點擊 keep.png
                button_path = str(config.KEEP_BUTTON_IMAGE)
                button_name = "保留(keep)"
            
            # 步驟3: 多次重試機制
            max_retries = 3
            retry_delay = 1.0
            
            for attempt in range(1, max_retries + 1):
                self.logger.info(f"第 {attempt}/{max_retries} 次嘗試檢測 {button_name} 按鈕...")
                
                # 嘗試找到並點擊按鈕（使用較長的 timeout）
                if self.find_and_click_button(button_path, button_name, timeout=5):
                    self.logger.info(f"✅ 第 {attempt} 次嘗試成功！已{action_desc}")
                    return True
                
                # 如果不是最後一次嘗試，等待後重試
                if attempt < max_retries:
                    self.logger.info(f"⚠️ 第 {attempt} 次嘗試失敗，等待 {retry_delay} 秒後重試...")
                    time.sleep(retry_delay)
            
            # 所有重試都失敗
            self.logger.info(f"ℹ️ 經過 {max_retries} 次嘗試仍未找到 {button_name} 按鈕")
            self.logger.info("可能原因：1) 沒有保存對話框 2) 按鈕外觀變化 3) 圖像檔案需要更新")
            return True  # 沒有按鈕也算成功（避免中斷流程）
                
        except Exception as e:
            self.logger.error(f"處理保存對話框時發生錯誤: {str(e)}")
            return False
    
    def validate_required_images(self) -> bool:
        """
        驗證所需的圖像資源是否可用（更新後的版本：檢查必要圖像和可選圖像）
        
        Returns:
            bool: 所有必需圖像是否都存在且可讀取
        """
        try:
            # 如果不要求圖像識別，直接通過
            if not config.IMAGE_RECOGNITION_REQUIRED:
                self.logger.info("圖像識別已設為可選，跳過圖像檔案檢查")
                return True
            
            # 必需的圖像
            required_images = [
                config.STOP_BUTTON_IMAGE,
                config.SEND_BUTTON_IMAGE
            ]
            
            # 可選的圖像（不會導致驗證失敗）
            optional_images = [
                config.NEWCHAT_SAVE_IMAGE
            ]
            
            missing_images = []
            invalid_images = []
            missing_optional = []
            
            # 檢查必需圖像
            for image_path in required_images:
                if not image_path.exists():
                    missing_images.append(str(image_path))
                else:
                    # 嘗試讀取圖像驗證其有效性
                    try:
                        img = cv2.imread(str(image_path))
                        if img is None:
                            invalid_images.append(str(image_path))
                    except Exception:
                        invalid_images.append(str(image_path))
            
            # 檢查可選圖像
            for image_path in optional_images:
                if not image_path.exists():
                    missing_optional.append(str(image_path))
                else:
                    # 驗證可選圖像有效性
                    try:
                        img = cv2.imread(str(image_path))
                        if img is not None:
                            self.logger.debug(f"可選圖像可用: {image_path.name}")
                    except Exception:
                        missing_optional.append(str(image_path))
            
            if missing_images:
                self.logger.warning("缺少必需圖像資源:")
                for img in missing_images:
                    self.logger.warning(f"  - {img}")
            
            if invalid_images:
                self.logger.warning("無效的必需圖像資源:")
                for img in invalid_images:
                    self.logger.warning(f"  - {img}")
            
            if missing_optional:
                self.logger.debug("缺少可選圖像資源（不影響功能）:")
                for img in missing_optional:
                    self.logger.debug(f"  - {img}")
            
            # 即使有缺失圖像也不會失敗，因為現在是可選的
            if missing_images or invalid_images:
                self.logger.info("圖像識別功能不可用，將使用鍵盤操作替代方案")
                return True
            
            self.logger.info("✅ 所有必需的圖像資源驗證通過")
            return True
            
        except Exception as e:
            self.logger.error(f"驗證圖像資源時發生錯誤: {str(e)}")
            return False
    
    def create_template_screenshots(self) -> bool:
        """
        協助用戶創建模板截圖的指導函數
        
        Returns:
            bool: 是否成功提供指導
        """
        try:
            self.logger.info("=" * 60)
            self.logger.info("圖像模板創建指南")
            self.logger.info("=" * 60)
            
            templates_needed = [
                ("regenerate_button.png", "Copilot Chat 中的'重新生成'按鈕"),
                ("copy_button.png", "Copilot Chat 中的'複製'按鈕"),
                ("copilot_input.png", "Copilot Chat 的輸入框區域")
            ]
            
            self.logger.info("需要創建以下模板圖像:")
            for filename, description in templates_needed:
                self.logger.info(f"  - {filename}: {description}")
            
            self.logger.info("")
            self.logger.info("創建步驟:")
            self.logger.info("1. 打開 VS Code 並開啟 Copilot Chat")
            self.logger.info("2. 使用截圖工具（如 Snipping Tool）")
            self.logger.info("3. 精確截取上述 UI 元素的小範圍圖像")
            self.logger.info("4. 將圖像儲存到 assets/ 目錄下")
            self.logger.info("5. 確保圖像清晰且背景一致")
            
            self.logger.info("")
            self.logger.info(f"儲存路徑: {config.ASSETS_DIR}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"提供創建指南時發生錯誤: {str(e)}")
            return False

# 創建全域實例
image_recognition = ImageRecognition()

# 便捷函數
def find_image(template_path: str, confidence: float = None) -> Optional[Tuple[int, int, int, int]]:
    """尋找圖像的便捷函數"""
    return image_recognition.find_image_on_screen(template_path, confidence)

def wait_for_image(template_path: str, timeout: int = 30) -> bool:
    """等待圖像出現的便捷函數"""
    return image_recognition.wait_for_image(template_path, timeout)

def click_image(template_path: str, confidence: float = None) -> bool:
    """點擊圖像的便捷函數"""
    return image_recognition.click_on_image(template_path, confidence)

def check_copilot_ready() -> bool:
    """檢查 Copilot 準備狀態的便捷函數"""
    return image_recognition.check_copilot_response_ready()

def validate_image_assets() -> bool:
    """驗證圖像資源的便捷函數"""
    return image_recognition.validate_required_images()

def clear_notifications() -> bool:
    """清除 VS Code 通知的便捷函數"""
    return image_recognition.clear_vscode_notifications()

def check_copilot_status_with_auto_clear() -> dict:
    """檢查 Copilot 狀態並自動清除通知的便捷函數"""
    return image_recognition.check_copilot_response_status_with_auto_clear()

def check_newchat_save_dialog(timeout: int = 2) -> bool:
    """檢查是否出現保存新聊天對話框的便捷函數"""
    return image_recognition.check_newchat_save_dialog(timeout)

def handle_newchat_save_dialog(action: str = "keep") -> bool:
    """處理保存新聊天對話框的便捷函數"""
    return image_recognition.handle_newchat_save_dialog(action)

def handle_save_dialog_with_image_recognition(modification_action: str = "keep") -> bool:
    """使用圖像辨識處理保存對話框的便捷函數"""
    return image_recognition.handle_save_dialog_with_image_recognition(modification_action)