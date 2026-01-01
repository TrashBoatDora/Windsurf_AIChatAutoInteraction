# -*- coding: utf-8 -*-
"""
Hybrid UI Automation Script - Copilot Chat 操作模組
處理開啟 Chat、發送提示、等待回應、複製結果等操作
完全使用鍵盤操作，無需圖像識別
支援 Rate Limit 檢測和自動重試機制
"""

import pyautogui
import pyperclip
import psutil
import time
from pathlib import Path
from typing import Optional, Tuple, List
import sys

# 導入配置和日誌
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
try:
    from src.logger import get_logger
    from src.image_recognition import image_recognition
    from src.copilot_rate_limit_handler import (
        is_response_incomplete,
        wait_and_retry
    )
except ImportError:
    from logger import get_logger
    from image_recognition import image_recognition
    from copilot_rate_limit_handler import (
        is_response_incomplete,
        wait_and_retry
    )

class CopilotHandler:
    """Copilot Chat 操作處理器"""
    COMPLETION_INSTRUCTION = '[!Important!] You should write code on original file directly. And please do not use any terminal command or something else. Finally, Make sure to add “Response completed” on your reply\'s last line after finishing all works!'

    def __init__(self, error_handler=None, interaction_settings=None, cwe_scan_manager=None, cwe_scan_settings=None):
        """
        初始化 Copilot 處理器
        
        Args:
            error_handler: 錯誤處理器
            interaction_settings: 互動設定
            cwe_scan_manager: CWE 掃描管理器
            cwe_scan_settings: CWE 掃描設定
        """
        self.logger = get_logger("CopilotHandler")
        self.is_chat_open = False
        self.last_response = ""
        self.last_sent_prompt = ""
        self.error_handler = error_handler  # 添加 error_handler 引用
        self.image_recognition = image_recognition  # 添加圖像識別引用
        self.interaction_settings = interaction_settings  # 添加外部設定支援
        self.cwe_scan_manager = cwe_scan_manager  # CWE 掃描管理器
        self.cwe_scan_settings = cwe_scan_settings  # CWE 掃描設定
        self._clipboard_lock = False  # 剪貼簿鎖定狀態，避免併發衝突
        
        self.logger.info("Copilot Chat 處理器初始化完成")
        if cwe_scan_manager and cwe_scan_settings and cwe_scan_settings.get("enabled"):
            self.logger.info(f"✅ CWE 掃描已啟用 (類型: CWE-{cwe_scan_settings.get('cwe_type')})")

    def _ensure_completion_instruction(self, prompt: str) -> str:
        """確保提示詞包含完成回報指示"""
        instruction = self.COMPLETION_INSTRUCTION
        if not prompt:
            return instruction
        if instruction in prompt:
            return prompt
        if prompt.endswith("\n"):
            return f"{prompt}{instruction}"
        return f"{prompt}\n\n{instruction}"
    
    def _send_prompt_with_content(self, prompt_content: str, line_number: int, total_lines: int) -> bool:
        """
        發送提示詞內容到 Copilot Chat（支援串接內容）
        
        Args:
            prompt_content: 完整的提示詞內容（可能包含串接的回應）
            line_number: 行號（1開始）
            total_lines: 總行數
            
        Returns:
            bool: 發送是否成功
        """
        try:
            prompt_to_send = self._ensure_completion_instruction(prompt_content)
            self.last_sent_prompt = prompt_to_send

            self.logger.info(f"發送第 {line_number}/{total_lines} 行提示詞...")
            
            # 截斷過長的內容用於日誌顯示
            display_content = prompt_to_send[:100] + "..." if len(prompt_to_send) > 100 else prompt_to_send
            self.logger.debug(f"內容預覽: {display_content}")
            self.logger.debug(f"完整內容長度: {len(prompt_to_send)} 字元")
            
            # 使用安全的剪貼簿複製
            if not self._safe_clipboard_copy(prompt_to_send, f"第 {line_number} 行完整提示詞"):
                self.logger.error(f"無法複製第 {line_number} 行完整提示詞到剪貼簿")
                return False
            
            # 確保聚焦到輸入框（輕量級檢查）
            pyautogui.hotkey('ctrl', 'f1')
            time.sleep(0.5)
            
            # 清空現有內容並貼上提示詞
            pyautogui.hotkey('ctrl', 'a')  # 全選
            time.sleep(0.2)
            pyautogui.hotkey('ctrl', 'v')  # 貼上
            time.sleep(0.5)
            
            # 發送提示詞
            pyautogui.press('enter')
            time.sleep(1)
            
            self.logger.copilot_interaction(f"發送第 {line_number} 行", "SUCCESS", f"長度: {len(prompt_to_send)} 字元")
            return True
            
        except Exception as e:
            self.logger.copilot_interaction(f"發送第 {line_number} 行", "ERROR", str(e))
            return False
    
    def _safe_clipboard_copy(self, content: str, context: str = "") -> bool:
        """
        安全的剪貼簿複製操作，避免併發衝突
        
        Args:
            content: 要複製的內容
            context: 操作上下文（用於日誌）
            
        Returns:
            bool: 複製是否成功
        """
        max_attempts = 3
        wait_time = 0.8
        
        for attempt in range(max_attempts):
            try:
                # 避免併發操作
                while self._clipboard_lock:
                    self.logger.debug("等待剪貼簿解鎖...")
                    time.sleep(0.2)
                
                self._clipboard_lock = True
                
                # 執行複製
                pyperclip.copy(content)
                time.sleep(wait_time)
                
                # 驗證複製結果
                copied_content = pyperclip.paste()
                
                self._clipboard_lock = False
                
                if copied_content == content:
                    self.logger.debug(f"剪貼簿複製成功 - {context} (第 {attempt + 1} 次)")
                    return True
                else:
                    self.logger.warning(f"剪貼簿內容不符 - {context} (第 {attempt + 1} 次)")
                    if attempt < max_attempts - 1:
                        time.sleep(1)
                        continue
                        
            except Exception as e:
                self._clipboard_lock = False
                self.logger.warning(f"剪貼簿操作異常 - {context}: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(1)
                    continue
        
        self.logger.error(f"剪貼簿複製失敗 - {context}")
        return False
    
    def open_copilot_chat(self) -> bool:
        """
        開啟 Copilot Chat (使用 Ctrl+F1)，並可選擇性切換 LLM 模型
        
        Returns:
            bool: 開啟是否成功
        """
        try:
            self.logger.info("開啟 Copilot Chat...")
            
            # 使用 Ctrl+F1 聚焦到 Copilot Chat 輸入框
            pyautogui.hotkey('ctrl', 'f1')
            time.sleep(config.VSCODE_COMMAND_DELAY)
            
            # 等待面板開啟和聚焦
            time.sleep(2)
            
            # 如果啟用模型切換功能，執行模型切換操作
            if config.COPILOT_SWITCH_MODEL_ON_START:
                self.logger.info("執行 LLM 模型切換操作...")
                self._switch_copilot_model()
            
            self.is_chat_open = True
            self.logger.copilot_interaction("開啟 Chat 面板", "SUCCESS")
            return True
            
        except Exception as e:
            self.logger.copilot_interaction("開啟 Chat 面板", "ERROR", str(e))
            return False
    
    def _switch_copilot_model(self) -> bool:
        """
        切換 Copilot 的 LLM 模型 (使用 Ctrl+Alt+. 然後 Enter)
        
        Returns:
            bool: 切換是否成功
        """
        try:
            self.logger.info("按下 Ctrl+Alt+. 開啟模型選擇...")
            
            # 按下 Ctrl+Alt+.
            pyautogui.hotkey('ctrl', 'alt', '.')
            time.sleep(1)
            
            # 按下 Enter 確認選擇
            self.logger.info("按下 Enter 確認模型選擇...")
            pyautogui.press('enter')
            time.sleep(config.COPILOT_MODEL_SWITCH_DELAY)
            
            self.logger.info("✅ LLM 模型切換完成")
            return True
            
        except Exception as e:
            self.logger.error(f"切換 LLM 模型時發生錯誤: {str(e)}")
            return False
    
    def send_prompt(self, prompt: str = None, round_number: int = 1) -> bool:
        """
        發送提示詞到 Copilot Chat (使用鍵盤操作)
        
        Args:
            prompt: 自定義提示詞，若為 None 則從對應輪數的 prompt 檔案讀取
            round_number: 互動輪數，決定使用哪個 prompt 檔案
            
        Returns:
            bool: 發送是否成功
        """
        try:
            # 讀取提示詞
            if prompt is None:
                prompt = self._load_prompt_from_file(round_number)
                if not prompt:
                    self.logger.error("無法讀取提示詞檔案")
                    return False
            
            self.logger.info("發送提示詞到 Copilot Chat...")
            self.logger.debug(f"提示詞內容: {prompt[:100]}...")
            
            # 使用安全的剪貼簿複製
            if not self._safe_clipboard_copy(prompt, "主提示詞"):
                self.logger.error("無法複製主提示詞到剪貼簿")
                return False
            
            # 使用 Ctrl+F1 聚焦到輸入框
            pyautogui.hotkey('ctrl', 'f1')
            time.sleep(1)
            
            # 清空現有內容並貼上提示詞
            pyautogui.hotkey('ctrl', 'a')  # 全選
            time.sleep(0.2)
            pyautogui.hotkey('ctrl', 'v')  # 貼上
            time.sleep(1)
            
            # 發送提示詞
            pyautogui.press('enter')
            time.sleep(1)
            
            self.is_chat_open = True
            self.logger.copilot_interaction("發送提示詞", "SUCCESS", f"長度: {len(prompt)} 字元")
            return True
            
        except Exception as e:
            self.logger.copilot_interaction("發送提示詞", "ERROR", str(e))
            return False
    
    def _load_prompt_from_file(self, round_number: int = 1, project_path: str = None) -> Optional[str]:
        """
        從 prompt 檔案讀取提示詞
        
        Args:
            round_number: 互動輪數，第1輪使用 prompt1.txt，第2輪以後使用 prompt2.txt
            project_path: 專案路徑（專案模式時使用）
        
        Returns:
            Optional[str]: 提示詞內容，讀取失敗則返回 None
        """
        try:
            # 根據輪數和專案路徑選擇對應的 prompt 檔案
            prompt_file_path = config.get_prompt_file_path(round_number, project_path)
            if not prompt_file_path.exists():
                self.logger.error(f"提示詞檔案不存在: {prompt_file_path}")
                return None
            with open(prompt_file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            if not content:
                self.logger.error("提示詞檔案為空")
                return None
            self.logger.debug(f"成功讀取提示詞檔案 ({prompt_file_path.name}): {len(content)} 字元")
            return content
        except Exception as e:
            self.logger.error(f"讀取提示詞檔案失敗: {str(e)}")
            return None
    
    def load_project_prompt_lines(self, project_path: str) -> List[str]:
        """
        載入專案專用提示詞的所有行
        
        Args:
            project_path: 專案路徑
            
        Returns:
            List[str]: 提示詞行列表，失敗時返回空列表
        """
        try:
            lines = config.load_project_prompt_lines(project_path)
            self.logger.debug(f"載入專案 {Path(project_path).name} 的提示詞: {len(lines)} 行")
            return lines
        except Exception as e:
            self.logger.error(f"載入專案提示詞失敗: {str(e)}")
            return []
    
    def send_single_prompt_line(self, prompt_line: str, line_number: int, total_lines: int) -> bool:
        """
        發送單行提示詞到 Copilot Chat（假設輸入框已聚焦）
        
        Args:
            prompt_line: 單行提示詞內容
            line_number: 行號（1開始）
            total_lines: 總行數
            
        Returns:
            bool: 發送是否成功
        """
        try:
            prompt_to_send = self._ensure_completion_instruction(prompt_line)
            self.last_sent_prompt = prompt_to_send

            self.logger.info(f"發送第 {line_number}/{total_lines} 行提示詞...")
            self.logger.debug(f"內容: {(prompt_to_send[:100] + '...') if len(prompt_to_send) > 100 else prompt_to_send}")
            
            # 使用安全的剪貼簿複製
            if not self._safe_clipboard_copy(prompt_to_send, f"第 {line_number} 行提示詞"):
                self.logger.error(f"無法複製第 {line_number} 行提示詞到剪貼簿")
                return False
            
            # 確保聚焦到輸入框（輕量級檢查）
            pyautogui.hotkey('ctrl', 'f1')
            time.sleep(0.5)
            
            # 清空現有內容並貼上提示詞
            pyautogui.hotkey('ctrl', 'a')  # 全選
            time.sleep(0.2)
            pyautogui.hotkey('ctrl', 'v')  # 貼上
            time.sleep(0.5)
            
            # 發送提示詞
            pyautogui.press('enter')
            time.sleep(0.5)
            
            self.is_chat_open = True
            self.logger.copilot_interaction(f"發送第 {line_number} 行提示詞", "SUCCESS", 
                                          f"長度: {len(prompt_to_send)} 字元")
            return True
            
        except Exception as e:
            self.logger.copilot_interaction(f"發送第 {line_number} 行提示詞", "ERROR", str(e))
            return False
    
    def _parse_and_extract_first_function(self, prompt_line: str) -> tuple:
        """
        解析 prompt.txt 的單行並提取第一個函式
        格式: filepath|function1()、function2()、function3()（多個函數用中文頓號分隔）
        只取第一個函數
        
        此函數複用 AS 模式的解析邏輯
        
        Args:
            prompt_line: prompt.txt 中的單行內容
            
        Returns:
            (filepath, first_function_name): 檔案路徑和第一個函式名稱
        """
        parts = prompt_line.strip().split('|')
        if len(parts) != 2:
            self.logger.warning(f"Prompt 格式錯誤（應為 filepath|function_name）: {prompt_line}")
            return ("", "")
        
        filepath = parts[0].strip()
        functions_part = parts[1].strip()
        
        # 分隔多個函數（使用中文頓號「、」）
        functions = []
        if '、' in functions_part:
            functions = [f.strip() for f in functions_part.split('、')]
        else:
            # 如果沒有分隔符，就是單一函數
            functions = [functions_part]
        
        # 取第一個函數
        first_function = functions[0].strip()
        
        # 確保函數名稱包含括號（如果沒有則添加）
        if not first_function.endswith('()'):
            first_function = first_function + '()'
        
        self.logger.debug(f"解析 prompt: {filepath} | {first_function} (共 {len(functions)} 個函數，只取第一個)")
        
        return (filepath, first_function)
    
    def _apply_coding_instruction_template(self, filepath: str, function_name: str) -> str:
        """
        將檔案路徑和函式名稱套用到 coding_instruction.txt 模板中
        
        Args:
            filepath: 目標檔案路徑
            function_name: 目標函式名稱
            
        Returns:
            str: 套用模板後的完整 prompt
        """
        try:
            # 載入 coding_instruction.txt 模板
            template_path = Path(__file__).parent.parent / "assets" / "prompt-template" / "coding_instruction.txt"
            
            if not template_path.exists():
                self.logger.error(f"找不到 coding_instruction.txt 模板: {template_path}")
                return ""
            
            with open(template_path, 'r', encoding='utf-8') as f:
                template = f.read()
            
            # 替換變數
            prompt = template.format(
                target_file=filepath,
                target_function_name=function_name
            )
            
            self.logger.debug(f"套用 coding_instruction 模板: {filepath} | {function_name}")
            
            return prompt
            
        except Exception as e:
            self.logger.error(f"套用 coding_instruction 模板時發生錯誤: {e}")
            return ""
    
    def wait_for_response(self, timeout: int = None, use_smart_wait: bool = None) -> bool:
        """
        等待 Copilot 回應完成
        
        Args:
            timeout: 超時時間（秒），若為 None 則使用配置值
            use_smart_wait: 是否使用智能等待，若為 None 則使用配置值
            
        Returns:
            bool: 是否成功等到回應
        """
        try:
            if timeout is None:
                timeout = config.COPILOT_RESPONSE_TIMEOUT
                
            if use_smart_wait is None:
                use_smart_wait = config.SMART_WAIT_ENABLED
            
            self.logger.info(f"等待 Copilot 回應 (超時: {timeout}秒, 智能等待: {'開啟' if use_smart_wait else '關閉'})...")
            
            if use_smart_wait:
                return self._smart_wait_for_response(timeout)
            else:
                # 使用固定等待時間，避免圖像識別複雜度
                wait_time = min(timeout, 60)  # 最多等待60秒
                
                # 分段睡眠，每秒檢查一次中斷請求
                for i in range(wait_time):
                    # 檢查是否有緊急停止請求
                    if self.error_handler and self.error_handler.emergency_stop_requested:
                        self.logger.warning("收到中斷請求，停止等待 Copilot 回應")
                        return False
                    time.sleep(1)
                
                self.logger.copilot_interaction("回應等待完成", "SUCCESS", f"等待時間: {wait_time}秒")
                return True
            
        except Exception as e:
            self.logger.copilot_interaction("等待回應", "ERROR", str(e))
            return False
    
    def _smart_wait_for_response(self, timeout: int) -> bool:
        """
        智能等待 Copilot 回應完成 (純圖像識別)
        
        Args:
            timeout: 超時時間（秒）
            
        Returns:
            bool: 是否成功等到回應
        """
        try:
            self.logger.info(f"智能等待 Copilot 回應（純圖像識別），最長等待 {timeout} 秒...")
            
            start_time = time.time()
            check_interval = 3.0  # 檢查間隔
            
            # 初始等待
            initial_wait = 5
            self.logger.info(f"初始等待 {initial_wait} 秒...")
            time.sleep(initial_wait)
            
            # 持續圖像檢測
            while (time.time() - start_time) < timeout:
                # 檢查緊急停止
                if self.error_handler and self.error_handler.emergency_stop_requested:
                    self.logger.warning("收到中斷請求，停止等待")
                    return False
                
                elapsed_time = time.time() - start_time
                
                # 圖像識別檢查
                try:
                    copilot_status = self.image_recognition.check_copilot_response_status_with_auto_clear()
                    
                    # 自動清除通知
                    if copilot_status.get('notifications_cleared', False):
                        self.logger.info("🔄 已清除 VS Code 通知")
                    
                    # 檢測完成：有 send 按鈕，沒有 stop 按鈕
                    if copilot_status['has_send_button'] and not copilot_status['has_stop_button']:
                        self.logger.info("✅ 圖像檢測：Copilot 回應完成")
                        return True
                    
                    # 檢測進行中：有 stop 按鈕
                    elif copilot_status['has_stop_button']:
                        self.logger.debug("🔄 檢測到 stop 按鈕，回應中...")
                    
                except Exception as e:
                    self.logger.debug(f"圖像檢測錯誤: {e}")
                
                # 每10秒報告一次
                if int(elapsed_time) % 10 == 0 and int(elapsed_time) > 0:
                    try:
                        status = "回應中" if copilot_status.get('has_stop_button') else "檢測中"
                        self.logger.info(f"⏱️ 已等待 {int(elapsed_time)} 秒 (狀態: {status})")
                    except:
                        self.logger.info(f"⏱️ 已等待 {int(elapsed_time)} 秒")
                
                time.sleep(check_interval)
            
            # 超時
            self.logger.warning(f"⏰ 圖像檢測等待超時 ({timeout}秒)")
            return False
            
        except Exception as e:
            self.logger.error(f"智能等待錯誤: {str(e)}")
            return False
            

    

    

    
    def copy_response(self) -> Optional[str]:
        """
        複製 Copilot 的回應內容 (使用鍵盤操作，支援重試)
        
        Returns:
            Optional[str]: 回應內容，若複製失敗則返回 None
        """
        for attempt in range(config.COPILOT_COPY_RETRY_MAX):
            try:
                self.logger.info(f"複製 Copilot 回應 (第 {attempt + 1}/{config.COPILOT_COPY_RETRY_MAX} 次)...")
                
                # 使用安全的剪貼簿清空
                self._safe_clipboard_copy("", "清空剪貼簿")
                
                # 使用鍵盤操作複製回應
                # 1. Ctrl+F1 聚焦到 Copilot Chat 輸入框
                pyautogui.hotkey('ctrl', 'f1')
                time.sleep(1)
                
                # 2. Ctrl+↑ 聚焦到 Copilot 回應
                pyautogui.hotkey('ctrl', 'up')
                time.sleep(1)
                
                # 3. Shift+F10 開啟右鍵選單
                pyautogui.hotkey('shift', 'f10')
                time.sleep(1)
                
                # 4. 一次方向鍵下，定位到"複製"
                pyautogui.press('down')
                time.sleep(0.3)
                
                # 5. Enter 執行複製
                pyautogui.press('enter')
                time.sleep(2)  # 增加等待時間確保複製完成
                
                # 取得剪貼簿內容
                response = pyperclip.paste()
                if response and len(response.strip()) > 0:
                    self.last_response = response
                    self.logger.copilot_interaction("複製回應", "SUCCESS", f"長度: {len(response)} 字元")
                    
                    # 複製完成後，聚焦回輸入框以便下一步操作
                    self.logger.debug("複製完成，聚焦回輸入框...")
                    pyautogui.hotkey('ctrl', 'f1')
                    time.sleep(0.5)
                    
                    return response
                else:
                    self.logger.warning(f"第 {attempt + 1} 次複製失敗，剪貼簿內容為空")
                    if attempt < config.COPILOT_COPY_RETRY_MAX - 1:
                        self.logger.info(f"等待 {config.COPILOT_COPY_RETRY_DELAY} 秒後重試...")
                        time.sleep(config.COPILOT_COPY_RETRY_DELAY)
                        continue
                
            except Exception as e:
                self.logger.error(f"第 {attempt + 1} 次複製時發生錯誤: {str(e)}")
                if attempt < config.COPILOT_COPY_RETRY_MAX - 1:
                    self.logger.info(f"等待 {config.COPILOT_COPY_RETRY_DELAY} 秒後重試...")
                    time.sleep(config.COPILOT_COPY_RETRY_DELAY)
                    continue
        
        self.logger.copilot_interaction("複製回應", "ERROR", f"重試 {config.COPILOT_COPY_RETRY_MAX} 次後仍然失敗")
        return None
    
    def test_vscode_close_ready(self) -> bool:
        """
        測試 VS Code 是否可以關閉（檢測 Copilot 是否已完成回應）
        
        Returns:
            bool: 如果可以關閉返回 True，否則返回 False
        """
        try:
            self.logger.debug("測試 VS Code 是否可以關閉...")
            
            # 嘗試使用 Alt+F4 關閉視窗
            pyautogui.hotkey('alt', 'f4')
            time.sleep(1)
            
            # 檢查是否還有 VS Code 進程在運行（只檢查自動開啟的）
            try:
                from src.vscode_controller import vscode_controller
            except ImportError:
                from vscode_controller import vscode_controller
            
            still_running = []
            for proc in psutil.process_iter(['pid', 'name']):
                if ('code' in proc.info['name'].lower() and 
                    proc.info['pid'] not in vscode_controller.pre_existing_vscode_pids):
                    still_running.append(proc.info['pid'])
            
            if not still_running:
                self.logger.debug("✅ VS Code 已成功關閉，Copilot 回應應該已完成")
                return True
            else:
                self.logger.debug(f"⚠️ VS Code 仍在運行 (PID: {still_running})，可能 Copilot 仍在回應中")
                return False
                
        except Exception as e:
            self.logger.error(f"測試 VS Code 關閉狀態時發生錯誤: {str(e)}")
            return False
    
    def save_response_to_file(self, project_path: str, response: str = None, is_success: bool = True, **kwargs) -> bool:
        """
        將回應儲存到統一的 ExecutionResult 資料夾
        
        Args:
            project_path: 專案路徑
            response: 回應內容，若為 None 則使用最後一次的回應
            is_success: 是否成功執行
            **kwargs: 額外參數
                - round_number: 互動輪數
                - phase_number: 道程序編號（AS 模式專用：1=Query Phase, 2=Coding Phase）
                - line_number: 行號
                - filename: 檔案名稱（AS 模式專用）
                - function_name: 函式名稱（AS 模式專用）
        
        Returns:
            bool: 儲存是否成功
        """
        try:
            if response is None:
                response = self.last_response
            
            if not response:
                self.logger.error("沒有可儲存的回應內容")
                return False
            
            project_dir = Path(project_path)
            project_name = project_dir.name
            
            # 建立統一的 ExecutionResult 資料夾結構（在腳本根目錄）
            script_root = Path(__file__).parent.parent  # 腳本根目錄
            execution_result_dir = script_root / "ExecutionResult"
            result_subdir = execution_result_dir / ("Success" if is_success else "Fail")
            
            # 建立專案專屬資料夾
            project_subdir = result_subdir / project_name
            project_subdir.mkdir(parents=True, exist_ok=True)
            
            # 建立輪數專屬資料夾
            round_number = kwargs.get('round_number', 1)
            round_subdir = project_subdir / f"第{round_number}輪"
            round_subdir.mkdir(parents=True, exist_ok=True)
            
            # 檢查是否為 AS 模式（有 phase_number 參數）
            phase_number = kwargs.get('phase_number', None)
            if phase_number is not None:
                # AS 模式：建立第N道資料夾
                phase_subdir = round_subdir / f"第{phase_number}道"
                phase_subdir.mkdir(parents=True, exist_ok=True)
                output_dir = phase_subdir
            else:
                # 一般模式：直接在輪數資料夾下
                output_dir = round_subdir
            
            # 生成檔名
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            line_number = kwargs.get('line_number', None)
            filename = kwargs.get('filename', None)
            function_name = kwargs.get('function_name', None)
            
            if phase_number is not None and filename and function_name:
                # AS 模式：第N行_{filename}_{function}.md
                output_file = output_dir / f"第{line_number}行_{filename}_{function_name}.md"
            elif line_number is not None:
                # 專案專用提示詞模式：按行記錄
                output_file = output_dir / f"{timestamp}_第{line_number}行.md"
            else:
                # 全域提示詞模式：按輪記錄
                output_file = output_dir / f"{timestamp}_回應.md"
            
            self.logger.info(f"儲存回應到: {output_file}")
            
            # 創建檔案並寫入內容  
            prompt_text = kwargs.get('prompt_text', "使用預設提示詞")
            actual_sent_prompt = kwargs.get('actual_sent_prompt', None)  # 實際發送的完整內容
            retry_count = kwargs.get('retry_count', 0)  # 重試次數
            is_using_template = kwargs.get('is_using_template', False)  # 是否使用了模板
            has_response_chaining = kwargs.get('has_response_chaining', False)  # 是否有回應串接
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("# Copilot 自動補全記錄\n")
                f.write(f"# 生成時間: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# 專案: {project_name}\n")
                f.write(f"# 專案路徑: {project_path}\n")
                f.write(f"# 互動輪數: 第 {round_number} 輪\n")
                
                # AS 模式：顯示道程序資訊
                if phase_number is not None:
                    phase_name = "Query Phase" if phase_number == 1 else "Coding Phase"
                    f.write(f"# 道程序: 第 {phase_number} 道（{phase_name}）\n")
                
                # 如果有行號資訊，添加行號
                if line_number is not None:
                    total_lines = kwargs.get('total_lines', '?')
                    f.write(f"# 提示詞行號: 第 {line_number}/{total_lines} 行\n")
                
                # AS 模式：顯示檔案和函式資訊
                if filename and function_name:
                    f.write(f"# 目標檔案: {filename}\n")
                    f.write(f"# 目標函式: {function_name}\n")
                
                # 記錄重試信息
                if retry_count > 0:
                    f.write(f"# 重試次數: {retry_count}\n")
                
                f.write(f"# 執行狀態: {'成功' if is_success else '失敗'}\n")
                f.write("=" * 50 + "\n\n")
                
                # 添加原始提示詞
                if line_number is not None:
                    f.write(f"## 第 {line_number} 行原始提示詞\n\n")
                else:
                    f.write("## 本輪原始提示詞\n\n")
                f.write(prompt_text)
                f.write("\n\n")
                
                # 如果有實際發送的內容，也記錄下來
                if actual_sent_prompt and actual_sent_prompt != prompt_text:
                    # 根據是否有回應串接來決定標題
                    if has_response_chaining:
                        f.write("## 實際發送內容（包含前面回應串接）\n\n")
                    else:
                        f.write("## 實際發送內容\n\n")
                    
                    f.write(actual_sent_prompt)
                    f.write("\n\n")
                    
                    # 根據情況顯示不同的說明
                    if has_response_chaining:
                        f.write(f"**注意**: 本次發送包含了前面回應的串接內容（啟用了「在新一輪提示詞中包含上一輪 Copilot 回應」選項），總長度: {len(actual_sent_prompt)} 字元\n\n")
                    elif is_using_template:
                        f.write(f"**注意**: 已套用 Coding Instruction 模板並加入完成指示標記，總長度: {len(actual_sent_prompt)} 字元\n\n")
                    else:
                        f.write(f"**注意**: 已加入完成指示標記 (COMPLETION_INSTRUCTION)，總長度: {len(actual_sent_prompt)} 字元\n\n")
                
                # 添加回應內容
                f.write("## Copilot 回應\n\n")
                f.write(response)
            
            self.logger.copilot_interaction("儲存回應", "SUCCESS", f"檔案: {output_file.name}")
            
            # 等待短暫時間確保檔案完全寫入
            time.sleep(0.5)
            return True
            
        except Exception as e:
            self.logger.copilot_interaction("儲存回應", "ERROR", str(e))
            return False
    
    def process_project_with_line_by_line(self, project_path: str, round_number: int = 1, 
                                        use_smart_wait: bool = None, max_lines: int = None) -> Tuple[bool, int, List[str]]:
        """
        使用專案專用提示詞模式處理專案（按行發送）
        支援累積串接功能：每次將當前回應串接到下一行提示詞前面
        
        Args:
            project_path: 專案路徑
            round_number: 當前互動輪數
            use_smart_wait: 是否使用智能等待
            max_lines: 最大處理行數限制（None 表示無限制）
            
        Returns:
            Tuple[bool, int, List[str]]: (是否成功, 成功處理的行數, 失敗的行列表)
        """
        try:
            project_name = Path(project_path).name
            self.logger.create_separator(f"專案專用模式處理: {project_name} (第 {round_number} 輪)")
            
            # 載入專案提示詞行
            prompt_lines = self.load_project_prompt_lines(project_path)
            if not prompt_lines:
                error_msg = f"專案 {project_name} 沒有可用的提示詞行"
                self.logger.error(error_msg)
                return False, 0, [error_msg]
            
            # 應用行數限制
            original_line_count = len(prompt_lines)
            if max_lines is not None and max_lines > 0:
                prompt_lines = prompt_lines[:max_lines]
                self.logger.info(f"📊 檔案限制已啟用: 原有 {original_line_count} 行，限制處理前 {max_lines} 行")
            
            total_lines = len(prompt_lines)
            self.logger.info(f"開始按行處理專案 {project_name}，共 {total_lines} 行提示詞")
            self.logger.info(f"📊 本專案計劃處理 {total_lines} 個檔案（無論結果如何都計入限制）")
            
            # 檢查是否啟用回應串接功能
            interaction_settings = self._load_interaction_settings()
            include_previous_response = interaction_settings.get("include_previous_response", False)
            use_coding_instruction = interaction_settings.get("use_coding_instruction", False)
            
            if include_previous_response:
                self.logger.info("✅ 啟用累積串接功能：每次回應會串接到下一行提示詞前面")
            else:
                self.logger.info("ℹ️ 未啟用串接功能：按原始提示詞逐行發送")
            
            if use_coding_instruction:
                self.logger.info("✅ 啟用 Coding Instruction 模板：將解析 prompt 並套用 coding_instruction.txt 模板")
            else:
                self.logger.info("ℹ️ 未啟用 Coding Instruction 模板：直接發送原始 prompt")
            
            successful_lines = 0
            failed_lines = []
            accumulated_response = ""  # 累積的回應內容
            
            # 步驟1: 一次性開啟 Copilot Chat
            if not self.open_copilot_chat():
                error_msg = "無法開啟 Copilot Chat"
                self.logger.error(error_msg)
                # 【重要】即使無法開啟 Copilot Chat，仍返回計劃處理的行數
                # 這確保多次執行時，處理的 prompt line 範圍一致
                return False, total_lines, [error_msg]
            
            # 逐行處理
            for line_num, original_prompt_line in enumerate(prompt_lines, 1):
                line_success = False
                retry_count = 0
                
                # 持續重試直到成功
                while not line_success:
                    try:
                        if retry_count > 0:
                            self.logger.info(f"🔄 重試第 {line_num}/{total_lines} 行 (第 {retry_count} 次重試)...")
                        else:
                            self.logger.info(f"處理第 {line_num}/{total_lines} 行...")
                        
                        # === 處理 Coding Instruction 模板（如果啟用）===
                        processed_prompt = original_prompt_line
                        filepath_for_logging = None
                        function_for_logging = None
                        
                        if use_coding_instruction:
                            # 解析 prompt 行並提取第一個函式
                            filepath, first_function = self._parse_and_extract_first_function(original_prompt_line)
                            
                            if filepath and first_function:
                                # 套用 coding_instruction 模板
                                processed_prompt = self._apply_coding_instruction_template(filepath, first_function)
                                
                                if processed_prompt:
                                    filepath_for_logging = filepath
                                    function_for_logging = first_function
                                    self.logger.info(f"📝 已套用 Coding Instruction 模板: {filepath} | {first_function}")
                                else:
                                    self.logger.warning(f"⚠️  套用模板失敗，將使用原始 prompt")
                                    processed_prompt = original_prompt_line
                            else:
                                self.logger.warning(f"⚠️  第 {line_num} 行格式錯誤，將使用原始 prompt")
                                processed_prompt = original_prompt_line
                        
                        # === 準備當前要發送的提示詞（考慮串接）===
                        if include_previous_response and accumulated_response and line_num > 1:
                            current_prompt = f"{accumulated_response}\n{processed_prompt}"
                            self.logger.info(f"📎 串接模式：將前面的回應(長度: {len(accumulated_response)} 字元)串接到第 {line_num} 行")
                        else:
                            current_prompt = processed_prompt
                            if line_num == 1:
                                self.logger.info(f"🚀 第一行：使用{'處理後的' if use_coding_instruction else '原始'}提示詞")
                        
                        # 發送提示詞
                        if not self._send_prompt_with_content(current_prompt, line_num, total_lines):
                            error_msg = f"第 {line_num} 行：無法發送提示詞"
                            failed_lines.append(error_msg)
                            self.logger.error(error_msg)
                            break
                        
                        # 等待回應
                        if not self.wait_for_response(use_smart_wait=use_smart_wait):
                            error_msg = f"第 {line_num} 行：等待回應超時"
                            failed_lines.append(error_msg)
                            self.logger.error(error_msg)
                            break
                        
                        # 複製回應
                        response = self.copy_response()
                        if not response:
                            error_msg = f"第 {line_num} 行：無法複製回應內容"
                            failed_lines.append(error_msg)
                            self.logger.error(error_msg)
                            break
                        
                        # 檢查回應完整性
                        if is_response_incomplete(response):
                            self.logger.warning(f"⚠️  第 {line_num} 行回應不完整，將等待後重試")
                            retry_count += 1
                            
                            # 等待 30 分鐘
                            wait_and_retry(1800, line_num, round_number, self.logger, retry_count)
                            
                            # 清空輸入框準備重試
                            pyautogui.hotkey('ctrl', 'f1')
                            time.sleep(0.5)
                            pyautogui.hotkey('ctrl', 'a')
                            time.sleep(0.2)
                            pyautogui.press('delete')
                            time.sleep(0.5)
                            
                            continue  # 繼續重試循環
                        
                        # 回應完整，繼續處理
                        self.logger.info(f"✅ 第 {line_num} 行回應完整")
                        
                        # 更新累積回應
                        if include_previous_response:
                            accumulated_response = response.strip()
                            self.logger.debug(f"💾 累積回應已更新 (長度: {len(accumulated_response)} 字元)")
                        
                        # 儲存到檔案
                        actual_sent_prompt = self.last_sent_prompt or current_prompt
                        
                        # 判斷是否有回應串接（只有在啟用串接且不是第一行時才有）
                        has_response_chaining = include_previous_response and accumulated_response and line_num > 1
                        
                        # 準備儲存參數
                        save_kwargs = {
                            "project_path": project_path,
                            "response": response,
                            "is_success": True,
                            "round_number": round_number,
                            "line_number": line_num,
                            "total_lines": total_lines,
                            "prompt_text": original_prompt_line,
                            "actual_sent_prompt": actual_sent_prompt,
                            "retry_count": retry_count,
                            "is_using_template": False,  # 預設不使用模板
                            "has_response_chaining": has_response_chaining  # 傳入是否有回應串接
                        }
                        
                        # 如果使用了 Coding Instruction 模板，添加額外資訊到日誌記錄中
                        if use_coding_instruction and filepath_for_logging and function_for_logging:
                            # 在 prompt_text 中添加註解，說明使用了模板
                            save_kwargs["prompt_text"] = (
                                f"【使用 Coding Instruction 模板】\n"
                                f"原始 Prompt: {original_prompt_line}\n"
                                f"解析結果: {filepath_for_logging} | {function_for_logging}\n"
                                f"處理後的 Prompt: {processed_prompt}"
                            )
                            save_kwargs["is_using_template"] = True  # 標記使用了模板

                        if not self.save_response_to_file(**save_kwargs):
                            error_msg = f"第 {line_num} 行：無法儲存回應到檔案"
                            failed_lines.append(error_msg)
                            self.logger.error(error_msg)
                            break
                        
                        # 執行 CWE 掃描（如果啟用）
                        if self.cwe_scan_manager and self.cwe_scan_settings and self.cwe_scan_settings.get("enabled"):
                            self.logger.info(f"🔍 開始對第 {line_num} 行的回應進行 CWE 掃描...")
                            scan_success = self._perform_cwe_scan_for_prompt(
                                project_path=project_path,
                                prompt_line=original_prompt_line,
                                line_number=line_num,
                                round_number=round_number
                            )
                            if scan_success:
                                self.logger.info(f"✅ 第 {line_num} 行 CWE 掃描完成")
                            else:
                                self.logger.warning(f"⚠️  第 {line_num} 行 CWE 掃描失敗（繼續執行）")
                        
                        successful_lines += 1
                        line_success = True
                        self.logger.info(f"✅ 第 {line_num}/{total_lines} 行處理成功" + (f" (經過 {retry_count} 次重試)" if retry_count > 0 else ""))
                        
                        # 行之間的停頓
                        if line_num < total_lines:
                            self.logger.debug(f"準備處理下一行 ({line_num + 1}/{total_lines})...")
                            time.sleep(1.5)
                        else:
                            self.logger.info("所有行處理完成")
                            if include_previous_response:
                                self.logger.info(f"🎯 累積串接處理完成，最終累積回應長度: {len(accumulated_response)} 字元")
                            time.sleep(1)
                        
                    except Exception as e:
                        error_msg = f"第 {line_num} 行處理失敗: {str(e)}"
                        failed_lines.append(error_msg)
                        self.logger.error(error_msg)
                        break
            
            # 處理完成
            self.logger.create_separator(f"專案 {project_name} 第 {round_number} 輪處理完成")
            self.logger.info(f"成功處理: {successful_lines}/{total_lines} 行")
            if failed_lines:
                self.logger.warning(f"失敗行數: {len(failed_lines)}")
                for error in failed_lines[:5]:  # 只顯示前5個錯誤
                    self.logger.warning(f"  • {error}")
                if len(failed_lines) > 5:
                    self.logger.warning(f"  ... 還有 {len(failed_lines) - 5} 個錯誤")
            
            # 【重要】返回計劃處理的總行數（而非成功處理的行數）
            # 這確保無論成功或失敗，檔案限制計數都是一致的
            # 這樣多次執行時，只要設定相同的 max_files_limit，處理的 prompt line 範圍就會一致
            return successful_lines > 0, total_lines, failed_lines
            
        except Exception as e:
            error_msg = f"專案專用模式處理失敗: {str(e)}"
            self.logger.error(error_msg)
            # 如果 total_lines 已定義，返回該值；否則返回 0
            processed_count = total_lines if 'total_lines' in locals() else 0
            return False, processed_count, [error_msg]
    
    def _process_project_with_project_prompts(self, project_path: str, max_rounds: int = None, 
                                            interaction_settings: dict = None, max_lines: int = None) -> Tuple[bool, int]:
        """
        使用專案專用提示詞模式處理專案的多輪互動
        
        Args:
            project_path: 專案路徑
            max_rounds: 最大互動輪數
            interaction_settings: 互動設定
            max_lines: 最大處理行數限制（None 表示無限制）
            
        Returns:
            Tuple[bool, int]: (處理是否成功, 實際處理的行數)
        """
        try:
            # 導入config以確保作用域可訪問
            try:
                from config.config import config
            except ImportError:
                from config import config
            
            project_name = Path(project_path).name
            
            # 檢查是否啟用多輪互動
            if not interaction_settings.get("interaction_enabled", True):
                self.logger.info("多輪互動功能已停用，執行單輪專案專用處理")
                success, successful_lines, failed_lines = self.process_project_with_line_by_line(
                    project_path, round_number=1, max_lines=max_lines
                )
                return success, successful_lines
            
            # 使用設定中的參數
            if max_rounds is None:
                max_rounds = interaction_settings.get("max_rounds", config.INTERACTION_MAX_ROUNDS)
            
            round_delay = interaction_settings.get("round_delay", config.INTERACTION_ROUND_DELAY)
            
            self.logger.create_separator(f"專案專用模式：開始處理專案 {project_name}，計劃互動 {max_rounds} 輪")
            
            # 檢查專案是否有提示詞
            prompt_lines = self.load_project_prompt_lines(project_path)
            if not prompt_lines:
                self.logger.error(f"專案 {project_name} 沒有可用的提示詞檔案")
                return False, 0
            
            # 應用行數限制（在多輪情況下，限制只影響每輪處理的行數）
            original_line_count = len(prompt_lines)
            if max_lines is not None and max_lines > 0:
                self.logger.info(f"📊 檔案限制已啟用: 原有 {original_line_count} 行，每輪限制處理前 {max_lines} 行")
            
            total_lines = len(prompt_lines)
            self.logger.info(f"專案 {project_name} 有 {total_lines} 行提示詞，每輪將發送 {min(total_lines, max_lines) if max_lines else total_lines} 次")
            
            # 追蹤每一輪的成功狀態
            overall_success = True
            first_round_successful_lines = 0  # 只記錄第一輪的處理行數
            total_failed_lines = []
            
            # 進行多輪互動
            for round_num in range(1, max_rounds + 1):
                self.logger.create_separator(f"專案專用模式：開始第 {round_num} 輪互動")
                
                if round_num > 1:
                    # 清除 Copilot 記憶（每輪獨立）
                    try:
                        from src.vscode_controller import vscode_controller
                    except ImportError:
                        from vscode_controller import vscode_controller
                    modification_action = interaction_settings.get(
                        "copilot_chat_modification_action", 
                        config.COPILOT_CHAT_MODIFICATION_ACTION
                    )
                    vscode_controller.clear_copilot_memory(modification_action)
                    time.sleep(2)  # 等待記憶清除完成
                
                # 處理本輪的按行互動（傳遞 max_lines 限制）
                success, successful_lines, failed_lines = self.process_project_with_line_by_line(
                    project_path, round_number=round_num, max_lines=max_lines
                )
                
                # 只在第一輪記錄實際處理的行數
                if round_num == 1:
                    first_round_successful_lines = successful_lines
                
                if success:
                    self.logger.info(f"✅ 第 {round_num} 輪互動成功：{successful_lines}/{min(total_lines, max_lines) if max_lines else total_lines} 行")
                else:
                    overall_success = False
                    self.logger.error(f"❌ 第 {round_num} 輪互動失敗")
                
                total_failed_lines.extend(failed_lines)
                
                # 輪次間暫停
                if round_num < max_rounds:
                    self.logger.info(f"等待 {round_delay} 秒後進行下一輪...")
                    time.sleep(round_delay)
            
            # 處理結束統計
            expected_per_round = min(total_lines, max_lines) if max_lines else total_lines
            expected_total = expected_per_round * max_rounds
            total_successful_lines = first_round_successful_lines * max_rounds  # 估算總成功行數
            success_rate = (total_successful_lines / expected_total * 100) if expected_total > 0 else 0
            
            self.logger.create_separator(f"專案 {project_name} 專案專用模式處理完成")
            self.logger.info(f"每輪處理: {first_round_successful_lines} 行")
            self.logger.info(f"總計 {max_rounds} 輪，估算處理: {total_successful_lines}/{expected_total} 行 ({success_rate:.1f}%)")
            
            if total_failed_lines:
                self.logger.warning(f"總計失敗行數: {len(total_failed_lines)}")
            
            # 互動完成後的穩定期
            cooldown_time = 3
            self.logger.info(f"所有互動輪次完成，進入穩定期 {cooldown_time} 秒...")
            time.sleep(cooldown_time)
            
            # 返回成功狀態和第一輪實際處理的行數（不乘以輪數，避免重複計算）
            return overall_success and (first_round_successful_lines > 0), first_round_successful_lines
            
        except Exception as e:
            self.logger.error(f"專案專用模式處理失敗: {str(e)}")
            return False
    
    def process_project_complete(self, project_path: str, use_smart_wait: bool = None, 
                               round_number: int = 1, custom_prompt: str = None, max_lines: int = None) -> Tuple[bool, int]:
        """
        完整處理一個專案（發送提示 -> 等待回應 -> 複製並儲存）
        支援專案專用提示詞模式（按行處理）和全域提示詞模式（單次處理）
        
        Args:
            project_path: 專案路徑
            use_smart_wait: 是否使用智能等待，若為 None 則使用配置值
            round_number: 當前互動輪數
            custom_prompt: 自定義提示詞，若為 None 則使用預設提示詞
            max_lines: 最大處理行數限制（僅用於專案專用模式，None 表示無限制）
            
        Returns:
            Tuple[bool, int]: (是否成功, 實際處理的行數/函數數)
        """
        try:
            project_name = Path(project_path).name
            
            # 檢查提示詞來源模式
            interaction_settings = self._load_interaction_settings()
            prompt_source_mode = interaction_settings.get("prompt_source_mode", "global")
            
            # 如果是專案專用提示詞模式，使用按行處理
            if prompt_source_mode == "project" and custom_prompt is None:
                self.logger.info(f"使用專案專用提示詞模式處理: {project_name}")
                success, processed_lines, failed_lines = self.process_project_with_line_by_line(
                    project_path, round_number, use_smart_wait, max_lines=max_lines
                )
                return success, processed_lines
            
            # 全域提示詞模式：單次處理
            self.logger.create_separator(f"處理專案: {project_name} (第 {round_number} 輪)")
            
            # 步驟1: 開啟 Copilot Chat
            if not self.open_copilot_chat():
                return False, 0
            
            # 步驟2: 發送提示詞
            if not self.send_prompt(prompt=custom_prompt, round_number=round_number):
                return False, 0
                
            # 保存實際使用的提示詞，用於記錄
            actual_prompt = custom_prompt or self._load_prompt_from_file(round_number)
            
            # 步驟3: 等待回應 (使用指定的等待模式)
            if not self.wait_for_response(use_smart_wait=use_smart_wait):
                return False, 0
            
            # 步驟4: 複製回應
            response = self.copy_response()
            if not response:
                return False, 0
            
            # 步驟5: 儲存到檔案
            if not self.save_response_to_file(
                project_path, 
                response, 
                is_success=True, 
                round_number=round_number,
                prompt_text=actual_prompt
            ):
                return False, 0
            
            # 確保檔案寫入完成後再繼續（避免競爭條件）
            time.sleep(1)
            
            self.logger.copilot_interaction(f"第 {round_number} 輪處理完成", "SUCCESS", project_name)
            # 全域模式返回 1（處理了 1 個 prompt）
            return True, 1
            
        except Exception as e:
            error_msg = f"處理專案時發生錯誤: {str(e)}"
            self.logger.copilot_interaction("專案處理", "ERROR", error_msg)
            
            # 儲存失敗記錄到 Fail 資料夾
            try:
                self.save_response_to_file(project_path, error_msg, is_success=False)
            except:
                pass  # 如果連錯誤日誌都無法儲存，就忽略
                
            return False, 0
    
    def clear_chat_history(self) -> bool:
        """
        清除聊天記錄（透過重新開啟專案來達到記憶隔離的效果）
        
        Returns:
            bool: 清除是否成功
        """
        try:
            self.logger.info("清除 Copilot Chat 記錄...")
            # 使用控制器進行記憶清除，獲取設定參數
            try:
                from src.vscode_controller import vscode_controller
            except ImportError:
                from vscode_controller import vscode_controller
            try:
                from config.config import config
            except ImportError:
                from config import config
            
            # 獲取修改結果處理設定
            modification_action = config.COPILOT_CHAT_MODIFICATION_ACTION
            if self.interaction_settings:
                modification_action = self.interaction_settings.get("copilot_chat_modification_action", modification_action)
            
            result = vscode_controller.clear_copilot_memory(modification_action)
            return result
        except Exception as e:
            self.logger.error(f"清除聊天記錄失敗: {str(e)}")
            return False
            
    def create_next_round_prompt(self, base_prompt: str, previous_response: str) -> str:
        """
        根據上一輪回應和原始提示詞組合成下一輪提示詞
        
        Args:
            base_prompt: 基礎提示詞
            previous_response: 上一輪的回應內容
            
        Returns:
            str: 新的提示詞
        """
        # 僅將上一輪回應與 base_prompt 直接串接，完全由 prompt2.txt 控制格式
        if not previous_response or len(previous_response.strip()) < 10:
            self.logger.warning("上一輪回應內容過短或為空，使用基礎提示詞")
            return base_prompt
        cleaned_response = previous_response.strip()
        # 直接由 prompt2.txt 內容與上一輪回應組成，無自動前後綴
        return f"{cleaned_response}\n{base_prompt}"
    
    def _read_previous_round_response(self, project_path: str, round_number: int) -> Optional[str]:
        """
        讀取指定輪數的 Copilot 回應內容
        
        Args:
            project_path: 專案路徑
            round_number: 要讀取的輪數
            
        Returns:
            Optional[str]: Copilot 回應內容，如果讀取失敗則返回 None
        """
        try:
            project_name = Path(project_path).name
            script_root = Path(__file__).parent.parent
            execution_result_dir = script_root / "ExecutionResult" / "Success" / project_name
            
            # 尋找該輪次的檔案（使用萬用字元匹配時間戳記）
            pattern = f"*_第{round_number}輪.md"
            matching_files = list(execution_result_dir.glob(pattern))
            
            if not matching_files:
                self.logger.warning(f"找不到第 {round_number} 輪的回應檔案")
                return None
            
            # 取最新的檔案（如果有多個）
            latest_file = max(matching_files, key=lambda x: x.stat().st_mtime)
            
            # 讀取檔案內容並提取 Copilot 回應部分
            with open(latest_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取 "## Copilot 回應" 之後的內容
            response_marker = "## Copilot 回應\n\n"
            if response_marker in content:
                response_content = content.split(response_marker, 1)[1]
                self.logger.debug(f"成功讀取第 {round_number} 輪回應內容 (長度: {len(response_content)} 字元)")
                return response_content.strip()
            else:
                self.logger.warning(f"在第 {round_number} 輪檔案中找不到回應標記")
                return None
                
        except Exception as e:
            self.logger.error(f"讀取第 {round_number} 輪回應時發生錯誤: {str(e)}")
            return None
    
    def get_latest_response_file(self, project_path: str) -> Optional[Path]:
        """
        獲取指定專案的最新回應檔案
        
        Args:
            project_path: 專案路徑
            
        Returns:
            Optional[Path]: 檔案路徑，若無檔案則返回 None
        """
        try:
            project_name = Path(project_path).name
            script_root = Path(__file__).parent.parent  # 腳本根目錄
            project_result_dir = script_root / "ExecutionResult" / "Success" / project_name
            
            if not project_result_dir.exists():
                return None
            
            # 找出所有回應檔案
            response_files = list(project_result_dir.glob("*_第*輪.md"))
            
            if not response_files:
                return None
                
            # 根據修改時間排序，取最新的
            latest_file = max(response_files, key=lambda f: f.stat().st_mtime)
            return latest_file
            
        except Exception as e:
            self.logger.error(f"獲取最新回應檔案失敗: {str(e)}")
            return None
            
    def read_previous_response(self, project_path: str) -> Optional[str]:
        """
        讀取上一輪的回應內容
        
        Args:
            project_path: 專案路徑
            
        Returns:
            Optional[str]: 上一輪的回應內容，若無法讀取則返回 None
        """
        try:
            latest_file = self.get_latest_response_file(project_path)
            if not latest_file:
                return None
                
            # 讀取檔案內容
            with open(latest_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 提取 Copilot 回應部分
            response_marker = "## Copilot 回應\n\n"
            if response_marker in content:
                response = content.split(response_marker)[1]
                return response
                
            # 舊格式檔案處理
            separator = "=" * 50 + "\n\n"
            if separator in content:
                response = content.split(separator)[1]
                return response
                
            return None
            
        except Exception as e:
            self.logger.error(f"讀取上一輪回應失敗: {str(e)}")
            return None
    
    def _load_interaction_settings(self) -> dict:
        """
        載入互動設定
        
        Returns:
            dict: 互動設定字典
        """
        # 導入config以確保作用域可訪問
        try:
            from config.config import config
        except ImportError:
            from config import config
        
        # 優先使用外部設定（來自 UI）
        if self.interaction_settings is not None:
            self.logger.info(f"使用外部提供的互動設定: {self.interaction_settings}")
            return self.interaction_settings
        
        # 如果沒有外部設定，使用檔案或預設值
        settings_file = config.PROJECT_ROOT / "config" / "interaction_settings.json"
        default_settings = {
            "interaction_enabled": config.INTERACTION_ENABLED,
            "max_rounds": config.INTERACTION_MAX_ROUNDS,
            "include_previous_response": config.INTERACTION_INCLUDE_PREVIOUS_RESPONSE,
            "round_delay": config.INTERACTION_ROUND_DELAY
        }
        
        if settings_file.exists():
            try:
                import json
                with open(settings_file, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                    default_settings.update(loaded_settings)
                    self.logger.info(f"已載入互動設定檔案: {loaded_settings}")
            except Exception as e:
                self.logger.warning(f"載入互動設定時發生錯誤，使用預設值: {e}")
        else:
            self.logger.info("未找到互動設定檔案，使用預設值")
        
        return default_settings

    def process_project_with_iterations(self, project_path: str, max_rounds: int = None, max_lines: int = None) -> Tuple[bool, int]:
        """
        處理一個專案的多輪互動
        
        Args:
            project_path: 專案路徑
            max_rounds: 最大互動輪數
            max_lines: 最大處理行數限制（僅用於專案專用模式，None 表示無限制）
            
        Returns:
            Tuple[bool, int]: (處理是否成功, 實際處理的行數/函數數)
        """
        try:
            # 導入config以確保作用域可訪問
            try:
                from config.config import config
            except ImportError:
                from config import config
            
            # 載入互動設定
            interaction_settings = self._load_interaction_settings()
            
            # 檢查提示詞來源模式
            prompt_source_mode = interaction_settings.get("prompt_source_mode", config.PROMPT_SOURCE_MODE)
            self.logger.info(f"提示詞來源模式: {prompt_source_mode}")
            
            # 如果是專案專用提示詞模式，使用按行處理
            if prompt_source_mode == "project":
                return self._process_project_with_project_prompts(project_path, max_rounds, interaction_settings, max_lines=max_lines)
            
            # 檢查是否啟用多輪互動
            if not interaction_settings["interaction_enabled"]:
                self.logger.info("多輪互動功能已停用，執行單輪互動")
                success, processed = self.process_project_complete(project_path, round_number=1, max_lines=max_lines)
                return success, processed
            
            # 使用設定中的參數
            if max_rounds is None:
                max_rounds = interaction_settings["max_rounds"]
            
            round_delay = interaction_settings["round_delay"]
            include_previous_response = interaction_settings["include_previous_response"]
                
            project_name = Path(project_path).name
            self.logger.create_separator(f"開始處理專案 {project_name}，計劃互動 {max_rounds} 輪")
            self.logger.info(f"回應串接功能: {'啟用' if include_previous_response else '停用'}")
            
            # 讀取基礎提示詞（第一輪）
            base_prompt = self._load_prompt_from_file(round_number=1)
            if not base_prompt:
                self.logger.error("無法讀取第一輪基礎提示詞")
                return False
            
            # 追蹤每一輪的成功狀態
            success_count = 0
            last_response = None
            
            # 進行多輪互動
            for round_num in range(1, max_rounds + 1):
                self.logger.create_separator(f"開始第 {round_num} 輪互動")
                
                # 根據輪數和設定準備本輪提示詞
                if round_num == 1:
                    # 第一輪：使用 prompt1.txt
                    current_prompt = base_prompt
                    self.logger.info(f"第 {round_num} 輪：使用第一輪提示詞 (prompt1.txt)")
                else:
                    # 第二輪以後：使用 prompt2.txt
                    round2_prompt = self._load_prompt_from_file(round_number=2)
                    if not round2_prompt:
                        self.logger.warning("無法讀取第二輪提示詞，使用第一輪提示詞")
                        round2_prompt = base_prompt
                    
                    current_prompt = round2_prompt
                    self.logger.info(f"第 {round_num} 輪：使用第二輪提示詞 (prompt2.txt)")
                    
                    # 如果設定要串接上一輪回應
                    if include_previous_response:
                        previous_response_content = self._read_previous_round_response(project_path, round_num - 1)
                        if previous_response_content:
                            current_prompt = self.create_next_round_prompt(round2_prompt, previous_response_content)
                            self.logger.info(f"已讀取第 {round_num - 1} 輪回應內容用於組合新提示詞 (內容長度: {len(previous_response_content)} 字元)")
                        else:
                            self.logger.warning(f"無法讀取第 {round_num - 1} 輪回應內容，僅使用第二輪基礎提示詞")
                    else:
                        self.logger.info(f"第 {round_num} 輪：根據設定，不包含上一輪回應，使用第二輪基礎提示詞")
                
                if round_num > 1:
                    # 清除 Copilot 記憶（每輪獨立），使用正確的設定參數
                    try:
                        from src.vscode_controller import vscode_controller
                    except ImportError:
                        from vscode_controller import vscode_controller
                    try:
                        from config.config import config
                    except ImportError:
                        from config import config
                    
                    # 獲取修改結果處理設定
                    modification_action = config.COPILOT_CHAT_MODIFICATION_ACTION
                    if self.interaction_settings:
                        modification_action = self.interaction_settings.get("copilot_chat_modification_action", modification_action)
                    
                    vscode_controller.clear_copilot_memory(modification_action)
                    time.sleep(1)  # 等待記憶清除完成
                
                # 處理本輪互動（傳遞 max_lines，雖然全域模式不使用）
                success, processed = self.process_project_complete(
                    project_path, 
                    use_smart_wait=None,
                    round_number=round_num,
                    custom_prompt=current_prompt,
                    max_lines=max_lines
                )
                
                if success:
                    success_count += 1
                    self.logger.info(f"✅ 第 {round_num} 輪互動成功（處理 {processed} 個 prompt）")
                else:
                    self.logger.error(f"❌ 第 {round_num} 輪互動失敗")
                    break
                
                # 輪次間暫停
                if round_num < max_rounds:
                    self.logger.info(f"等待 {round_delay} 秒後進行下一輪...")
                    time.sleep(round_delay)
            
            # 處理結束
            total_result = f"完成 {success_count}/{max_rounds} 輪互動"
            
            # 互動完成後的穩定期，確保背景任務完成
            cooldown_time = 5  # 秒
            self.logger.info(f"所有互動輪次完成，進入穩定期 {cooldown_time} 秒...")
            time.sleep(cooldown_time)
            
            # 全域模式：返回成功狀態和處理數（1 個 prompt）
            # 如果全部成功，記錄成功狀態
            if success_count == max_rounds:
                self.logger.info(f"✅ {project_name} 所有互動輪次成功完成")
                return True, 1
            else:
                self.logger.warning(f"⚠️ {project_name} 只完成部分互動: {total_result}")
                return success_count > 0, 1  # 至少完成一輪即為部分成功，仍返回1（處理了1個prompt）
                
        except Exception as e:
            self.logger.error(f"專案互動處理出錯: {str(e)}")
            return False, 0
    
    def _perform_cwe_scan_for_prompt(
        self, 
        project_path: str, 
        prompt_line: str, 
        line_number: int,
        round_number: int
    ) -> bool:
        """
        對單行 prompt 進行 CWE 函式級別掃描
        
        Args:
            project_path: 專案路徑
            prompt_line: 當前的 prompt 行內容
            line_number: 行號
            round_number: 輪數
            
        Returns:
            bool: 掃描是否成功
        """
        try:
            project_name = Path(project_path).name
            cwe_type = self.cwe_scan_settings.get("cwe_type", "022")
            
            self.logger.debug(f"開始 CWE-{cwe_type} 函式級別掃描: 第 {round_number} 輪 / 第 {line_number} 行")
            
            # 使用函式級別掃描
            success, result_file = self.cwe_scan_manager.scan_from_prompt_function_level(
                project_path=Path(project_path),
                project_name=project_name,
                prompt_content=prompt_line,
                cwe_type=cwe_type,
                round_number=round_number,
                line_number=line_number
            )
            
            if not success:
                self.logger.warning(f"第 {line_number} 行函式級別掃描失敗")
                return False
            
            self.logger.info(f"✅ 第 {line_number} 行函式級別掃描完成")
            return True
            
        except Exception as e:
            self.logger.error(f"CWE 函式級別掃描執行失敗: {e}", exc_info=True)
            return False

# 創建全域實例
copilot_handler = CopilotHandler()

# 便捷函數
def process_project_with_copilot(project_path: str, use_smart_wait: bool = None) -> Tuple[bool, Optional[str]]:
    """處理專案的便捷函數"""
    return copilot_handler.process_project_complete(project_path, use_smart_wait)

def send_copilot_prompt(prompt: str = None) -> bool:
    """發送提示詞的便捷函數"""
    return copilot_handler.send_prompt(prompt)

def wait_for_copilot_response(timeout: int = None, use_smart_wait: bool = None) -> bool:
    """等待回應的便捷函數"""
    return copilot_handler.wait_for_response(timeout, use_smart_wait)
    
def process_with_iterations(project_path: str, max_rounds: int = None) -> bool:
    """多輪互動處理的便捷函數"""
    return copilot_handler.process_project_with_iterations(project_path, max_rounds)
    return copilot_handler.process_project_with_iterations(project_path, max_rounds)