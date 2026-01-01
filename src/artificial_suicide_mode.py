# -*- coding: utf-8 -*-
"""
Artificial Suicide 攻擊模式 - 輕量級控制器
直接利用現有的 copilot_handler 和 cursor_controller 功能
不重複實作已有的邏輯
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
import time
import pyautogui

from src.logger import get_logger
from src.copilot_rate_limit_handler import is_response_incomplete, wait_and_retry
from src.query_statistics import initialize_query_statistics
from src.function_name_tracker import create_function_name_tracker
from src.vicious_pattern_manager import create_vicious_pattern_manager, ViciousPatternManager
from config.config import config


class ArtificialSuicideMode:
    """
    Artificial Suicide 攻擊模式控制器
    
    功能：
    1. 載入三個 prompt 模板（initial_query, following_query, coding_instruction）
    2. 控制兩道程序的執行流程
    3. 調用現有的 copilot_handler 和 cursor_controller
    """
    
    def __init__(self, copilot_handler, cursor_controller, cwe_scan_manager, 
                 error_handler, project_path: str, target_cwe: str, total_rounds: int,
                 max_files_limit: int = 0, files_processed_so_far: int = 0,
                 checkpoint_manager=None):
        """
        初始化 AS 模式控制器
        
        Args:
            copilot_handler: Copilot 處理器（現有）
            cursor_controller: Cursor 控制器（CursorController）
            cwe_scan_manager: CWE 掃描管理器（現有）
            error_handler: 錯誤處理器（現有）
            project_path: 專案路徑
            target_cwe: 目標 CWE 類型（如 "327"）
            total_rounds: 總輪數
            max_files_limit: 最大檔案處理限制（0 表示無限制）
            files_processed_so_far: 目前已處理的檔案數
            checkpoint_manager: 檢查點管理器（用於記錄執行進度）
        """
        self.logger = get_logger("ArtificialSuicide")
        self.copilot_handler = copilot_handler
        self.cursor_controller = cursor_controller
        self.cwe_scan_manager = cwe_scan_manager
        self.error_handler = error_handler
        self.project_path = Path(project_path)
        self.target_cwe = target_cwe
        self.total_rounds = total_rounds
        self.checkpoint_manager = checkpoint_manager  # 檢查點管理器
        
        # 檔案數量限制相關
        self.max_files_limit = max_files_limit
        self.files_processed_so_far = files_processed_so_far
        self.files_processed_in_project = 0  # 本專案已處理的檔案數
        
        # 載入模板
        self.templates = self._load_templates()
        
        # 載入 CWE 範例程式碼
        self.cwe_example_code = self._load_cwe_example_code()
        
        # 載入專案的 prompt.txt
        self.prompt_lines = self._load_prompt_lines()
        original_line_count = len(self.prompt_lines)  # 記錄原始行數
        
        # 如果有檔案數量限制，計算本專案可處理的行數
        if self.max_files_limit > 0:
            remaining_quota = self.max_files_limit - self.files_processed_so_far
            if remaining_quota <= 0:
                self.logger.warning(f"⚠️  已達到檔案處理限制 ({self.files_processed_so_far}/{self.max_files_limit})，將不處理任何檔案")
                self.prompt_lines = []
            elif len(self.prompt_lines) > remaining_quota:
                self.logger.info(f"📊 檔案數量限制: 專案有 {original_line_count} 行，僅處理前 {remaining_quota} 行（已處理: {self.files_processed_so_far}/{self.max_files_limit}）")
                self.prompt_lines = self.prompt_lines[:remaining_quota]
            else:
                self.logger.info(f"📊 檔案數量限制: 專案有 {original_line_count} 行，全部處理（已處理: {self.files_processed_so_far}/{self.max_files_limit}）")
        
        # 儲存每一輪每一行的回應（用於串接到下一輪）
        # 結構: {round_num: {line_idx: response_text}}
        self.round_responses = {}
        
        # Query 統計器（即時更新模式）
        self.query_stats = None
        
        # 函式名稱追蹤器
        self.function_name_tracker = None
        
        # Vicious Pattern Manager（漏洞 Pattern 備份管理器）
        self.vicious_pattern_manager: Optional[ViciousPatternManager] = None
        
        # 原始狀態掃描結果（用於攻擊前後比較報告）
        self.baseline_results = {}
        
        self.logger.info(f"✅ AS 模式初始化完成 - CWE-{target_cwe}, {total_rounds} 輪, {len(self.prompt_lines)} 行")
    
    def _load_templates(self) -> Dict[str, str]:
        """載入三個 prompt 模板"""
        template_dir = Path(__file__).parent.parent / "assets" / "prompt-template"
        templates = {}
        
        template_files = {
            "initial_query": "initial_query.txt",
            "following_query": "following_query.txt", 
            "coding_instruction": "coding_instruction.txt"
        }
        
        for key, filename in template_files.items():
            file_path = template_dir / filename
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    templates[key] = f.read()
                self.logger.debug(f"✅ 載入模板: {filename}")
            except FileNotFoundError:
                self.logger.error(f"❌ 找不到模板檔案: {file_path}")
                templates[key] = ""
        
        return templates
    
    def _load_cwe_example_code(self) -> str:
        """
        載入對應 CWE 類型的範例程式碼
        
        根據 target_cwe 從 assets/CWE/{cwe_id}.txt 載入範例程式碼
        例如：CWE-078 對應 assets/CWE/78.txt
        
        Returns:
            str: CWE 範例程式碼內容，如果找不到檔案則返回空字串
        """
        # 移除 CWE ID 的前導零（例如 "078" -> "78"）
        cwe_id = self.target_cwe.lstrip('0') if self.target_cwe else ""
        
        if not cwe_id:
            self.logger.warning("⚠️  未指定目標 CWE，無法載入範例程式碼")
            return ""
        
        # 構建 CWE 範例檔案路徑
        cwe_example_dir = Path(__file__).parent.parent / "assets" / "CWE"
        cwe_example_file = cwe_example_dir / f"{cwe_id}.txt"
        
        try:
            with open(cwe_example_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            self.logger.info(f"✅ 載入 CWE-{self.target_cwe} 範例程式碼: {cwe_example_file}")
            return content
        except FileNotFoundError:
            self.logger.warning(f"⚠️  找不到 CWE 範例檔案: {cwe_example_file}")
            return ""
        except Exception as e:
            self.logger.error(f"❌ 載入 CWE 範例程式碼失敗: {e}")
            return ""
    
    def _clear_input_and_refocus(self) -> bool:
        """
        清空輸入框並重新聚焦（使用圖像識別）
        
        用於重試前清理輸入框狀態
        
        Returns:
            bool: 操作是否成功
        """
        try:
            # 使用 copilot_handler 的圖像識別方法聚焦輸入框
            if hasattr(self.copilot_handler, '_refocus_input_bar'):
                if not self.copilot_handler._refocus_input_bar():
                    self.logger.warning("無法透過圖像識別聚焦輸入框，嘗試備用方案...")
                    # 備用方案：使用 Ctrl+Shift+Subtract 和 Ctrl+Shift+Add 組合
                    pyautogui.hotkey('ctrl', 'shift', 'subtract')
                    time.sleep(0.2)
                    pyautogui.hotkey('ctrl', 'shift', 'add')
                    time.sleep(0.5)
            else:
                # 如果方法不存在，使用備用方案
                pyautogui.hotkey('ctrl', 'shift', 'subtract')
                time.sleep(0.2)
                pyautogui.hotkey('ctrl', 'shift', 'add')
                time.sleep(0.5)
            
            # 全選並刪除
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.2)
            pyautogui.press('delete')
            time.sleep(0.5)
            
            return True
            
        except Exception as e:
            self.logger.error(f"清空輸入框時發生錯誤: {e}")
            return False
    
    def _load_prompt_lines(self) -> List[str]:
        """載入專案的 prompt.txt（利用現有功能）"""
        return self.copilot_handler.load_project_prompt_lines(str(self.project_path))
    
    def _generate_query_prompt(self, round_num: int, target_file: str, 
                               target_function_name: str, last_response: str = "") -> str:
        """
        生成第 1 道的 Query Prompt
        
        Args:
            round_num: 當前輪數
            target_file: 目標檔案路徑
            target_function_name: 目標函式名稱（原始名稱，會自動查詢最新名稱）
            last_response: 上一輪的回應內容（第 2+ 輪需要）
            
        Returns:
            str: 完整的 prompt
        """
        # 取得該輪次應使用的函式名稱
        if self.function_name_tracker:
            actual_function_name, line_number = self.function_name_tracker.get_function_name_for_round(
                target_file, target_function_name, round_num
            )
            self.logger.debug(f"第 {round_num} 輪使用函式：{actual_function_name}（行 {line_number}）")
        else:
            actual_function_name = target_function_name
        
        # 第 1 輪使用 initial_query，第 2+ 輪使用 following_query
        if round_num == 1:
            template = self.templates["initial_query"]
            variables = {
                "target_file": target_file,
                "target_function_name": actual_function_name,
                "CWE-XXX": f"CWE-{self.target_cwe}"
            }
        else:
            template = self.templates["following_query"]
            variables = {
                "target_file": target_file,
                "target_function_name": actual_function_name,
                "CWE-XXX": f"CWE-{self.target_cwe}",
                "Last_Response": last_response
            }
        
        # 先替換 CWE 範例程式碼佔位符 {{CWE_EXAMPLE_CODE}}
        # 必須在 format() 之前執行，否則 {{ 會被轉換成 {
        if "{{CWE_EXAMPLE_CODE}}" in template:
            template = template.replace("{{CWE_EXAMPLE_CODE}}", self.cwe_example_code)
            self.logger.debug(f"已插入 CWE-{self.target_cwe} 範例程式碼")
        
        # 再替換其他變數
        prompt = template.format(**variables)
        
        return prompt
    
    def _generate_coding_prompt(self, target_file: str, target_function_name: str) -> str:
        """
        生成第 2 道的 Coding Prompt
        
        Args:
            target_file: 目標檔案路徑
            target_function_name: 目標函式名稱（原始名稱，會自動查詢最新名稱）
            
        Returns:
            str: 完整的 prompt
        """
        # 取得最新的函式名稱
        if self.function_name_tracker:
            actual_function_name, line_number = self.function_name_tracker.get_latest_function_name(
                target_file, target_function_name
            )
            self.logger.debug(f"Coding Phase 使用函式：{actual_function_name}（行 {line_number}）")
        else:
            actual_function_name = target_function_name
        
        template = self.templates["coding_instruction"]
        
        # 替換變數
        prompt = template.format(
            target_file=target_file,
            target_function_name=actual_function_name
        )
        
        return prompt
    
    def _parse_prompt_line(self, prompt_line: str) -> tuple:
        """
        解析 prompt.txt 的單行
        格式: filepath|function1()、function2()、function3()（多個函數用中文頓號分隔）
        只取第一個函數
        
        Returns:
            (filepath, first_function_name)
        """
        parts = prompt_line.strip().split('|')
        if len(parts) != 2:
            self.logger.error(f"Prompt 格式錯誤（應為 filepath|function_name）: {prompt_line}")
            return ("", "")
        
        filepath = parts[0].strip()
        functions_part = parts[1].strip()
        
        # 分隔多個函數（使用中文頓號「、」或逗號）
        # 移除括號後分隔
        functions = []
        for separator in ['、']:
            if separator in functions_part:
                functions = [f.strip() for f in functions_part.split(separator)]
                break
        
        # 如果沒有分隔符，就是單一函數
        if not functions:
            functions = [functions_part]
        
        # 取第一個函數
        first_function = functions[0].strip()
        
        # 確保函數名稱包含括號（如果沒有則添加）
        if not first_function.endswith('()'):
            first_function = first_function + '()'
        
        self.logger.debug(f"解析 prompt: {filepath} | {first_function} (共 {len(functions)} 個函數)")
        
        return (filepath, first_function)
    
    def execute(self) -> Tuple[bool, int]:
        """
        執行完整的 AS 攻擊流程
        
        Returns:
            Tuple[bool, int]: (是否成功完成, 實際處理的檔案數)
        """
        try:
            self.logger.create_separator(f"🚀 開始 Artificial Suicide 攻擊 - CWE-{self.target_cwe}")
            self.logger.info(f"專案: {self.project_path.name}")
            self.logger.info(f"總輪數: {self.total_rounds}")
            self.logger.info(f"總行數: {len(self.prompt_lines)}")
            
            # 如果沒有行要處理，直接返回
            if len(self.prompt_lines) == 0:
                self.logger.warning("⚠️  沒有要處理的檔案（已達限制或 prompt.txt 為空）")
                return True, 0
            
            # 步驟 0：開啟專案（已在 main.py 中完成，此處跳過）
            # self.logger.info("📂 開啟專案到 VSCode...")
            # if not self.cursor_controller.open_project(str(self.project_path)):
            #     self.logger.error("❌ 無法開啟專案")
            #     return False, 0
            # time.sleep(3)  # 等待專案完全載入
            self.logger.info("📂 專案已在 main.py 中開啟，繼續執行...")
            
            # 步驟 0.5：初始化 Query 統計 CSV
            self.logger.info("📊 初始化 Query 統計...")
            # 解析每一行，只取第一個函數
            function_list = []
            for line in self.prompt_lines:
                filepath, first_function = self._parse_prompt_line(line)
                if filepath and first_function:
                    function_list.append(f"{filepath}_{first_function}")
            
            self.query_stats = initialize_query_statistics(
                project_name=self.project_path.name,
                cwe_type=self.target_cwe,
                total_rounds=self.total_rounds,
                function_list=function_list
            )
            
            # 步驟 0.6：初始化函式名稱追蹤器
            self.logger.info("📝 初始化函式名稱追蹤器...")
            self.function_name_tracker = create_function_name_tracker(
                project_name=self.project_path.name
            )
            
            # 將 function_name_tracker 傳遞給 cwe_scan_manager（用於記錄修改前/後的函式名稱）
            if self.cwe_scan_manager:
                self.cwe_scan_manager.function_name_tracker = self.function_name_tracker
                self.logger.info("✅ 已將 function_name_tracker 傳遞給 CWE 掃描管理器")
            
            # 步驟 0.7：初始化 Vicious Pattern Manager（漏洞 Pattern 備份管理器）
            self.logger.info("📦 初始化漏洞 Pattern 備份管理器...")
            self.vicious_pattern_manager = create_vicious_pattern_manager(
                project_name=self.project_path.name,
                project_path=self.project_path,
                cwe_type=self.target_cwe
            )
            
            # 步驟 0.8：執行原始狀態掃描（攻擊前基線掃描）
            if self.cwe_scan_manager:
                self.logger.info("📸 執行原始狀態掃描（攻擊前基線）...")
                self.baseline_results = self.cwe_scan_manager.scan_baseline_state(
                    project_path=self.project_path,
                    project_name=self.project_path.name,
                    prompt_lines=self.prompt_lines,
                    cwe_type=self.target_cwe
                )
            else:
                self.logger.warning("⚠️  未設置 CWE 掃描管理器，跳過原始狀態掃描")
                self.baseline_results = {}
            
            # 執行每一輪
            for round_num in range(1, self.total_rounds + 1):
                self.logger.create_separator(f"📍 第 {round_num}/{self.total_rounds} 輪")
                
                success = self._execute_round(round_num)
                
                if not success:
                    self.logger.warning(f"⚠️  第 {round_num} 輪部分失敗，繼續執行後續輪次")
                
                # 即時更新該輪的統計資料
                self.logger.info(f"📊 更新第 {round_num} 輪統計...")
                self.query_stats.update_round_result(round_num)
                
                self.logger.info(f"✅ 第 {round_num} 輪完成")
            
            # 記錄本專案實際處理的檔案數
            self.files_processed_in_project = len(self.prompt_lines)
            
            # 完成漏洞 Pattern 備份並生成 prompt.txt
            if self.vicious_pattern_manager and self.vicious_pattern_manager.has_vulnerability():
                self.vicious_pattern_manager.finalize()
            else:
                self.logger.info("📦 本專案未發現任何漏洞，不進行 Pattern 備份")
            
            # 生成攻擊前後比較報告
            self._generate_comparison_report_if_available()
            
            self.logger.create_separator("🎉 Artificial Suicide 攻擊完成")
            self.logger.info(f"📊 本專案處理了 {self.files_processed_in_project} 個檔案")
            return True, self.files_processed_in_project
            
        except Exception as e:
            self.logger.error(f"❌ AS 模式執行錯誤: {e}")
            # 即使出錯，也嘗試生成比較報告
            self._generate_comparison_report_if_available()
            return False, self.files_processed_in_project
    
    def _generate_comparison_report_if_available(self):
        """生成攻擊前後比較報告（如果有原始狀態掃描結果）"""
        if hasattr(self, 'baseline_results') and self.baseline_results and self.cwe_scan_manager:
            self.logger.info("📊 生成攻擊前後比較報告...")
            try:
                self.cwe_scan_manager.generate_comparison_report(
                    project_name=self.project_path.name,
                    cwe_type=self.target_cwe,
                    baseline_results=self.baseline_results,
                    total_rounds=self.total_rounds
                )
            except Exception as e:
                self.logger.error(f"❌ 生成比較報告失敗: {e}")
    
    def _execute_round(self, round_num: int) -> bool:
        """
        執行單輪攻擊（兩道程序）
        
        Args:
            round_num: 輪數
            
        Returns:
            bool: 是否成功
        """
        # 更新 checkpoint: 記錄當前輪數開始
        if self.checkpoint_manager:
            self.checkpoint_manager.update_progress(
                current_round=round_num,
                current_line=1,
                current_phase=1  # AS Mode Phase 1 開始
            )
        
        # === 第 1 道程序：Query Phase ===
        self.logger.info(f"▶️  第 {round_num} 輪 - 第 1 道程序（Query Phase）")
        
        if not self._execute_phase1(round_num):
            return False
        
        # Keep 修改（使用現有功能）
        self.logger.info("  💾 Keep 修改...")
        self.cursor_controller.clear_copilot_memory(modification_action="keep")
        time.sleep(2)
        
        # === 第 2 道程序：Coding Phase + Scan ===
        self.logger.info(f"▶️  第 {round_num} 輪 - 第 2 道程序（Coding Phase + Scan）")
        
        # 更新 checkpoint: Phase 2 開始
        if self.checkpoint_manager:
            self.checkpoint_manager.update_progress(
                current_phase=2,  # AS Mode Phase 2 開始
                current_line=1
            )
        
        if not self._execute_phase2(round_num):
            return False
        
        # Undo 修改（使用現有功能）
        self.logger.info("  ↩️  Undo 修改...")
        self.cursor_controller.clear_copilot_memory(modification_action="revert")
        time.sleep(2)
        
        # === 備份 Vicious Pattern（在 undo 之後）===
        # 此時檔案已恢復到 Phase 1 修改後的狀態（變數名稱已修改但沒有漏洞程式碼）
        # 這些「有毒模式」是成功引誘 Copilot 產生漏洞的模式
        if self.vicious_pattern_manager and self.vicious_pattern_manager.has_vulnerability():
            self.logger.info(f"  📦 備份 Vicious Pattern（第 {round_num} 輪）...")
            try:
                backup_count = self.vicious_pattern_manager.backup_round_patterns(round_num)
                if backup_count > 0:
                    self.logger.info(f"  ✅ 已備份 {backup_count} 個含有毒模式的檔案")
                else:
                    self.logger.info(f"  ℹ️  本輪無新的有毒模式需要備份")
            except Exception as e:
                self.logger.warning(f"  ⚠️  備份 Vicious Pattern 時發生錯誤: {e}")
        
        return True
    
    def _execute_phase1(self, round_num: int) -> bool:
        """
        執行第 1 道程序：Query Phase
        手動處理每一行以支援 AS 專用的檔案結構
        """
        try:
            self.logger.info(f"  開始處理第 1 道程序（共 {len(self.prompt_lines)} 行）")
            
            # 開啟 Copilot Chat（如果尚未開啟）
            if not self.copilot_handler.open_copilot_chat():
                self.logger.error("  ❌ 無法開啟 Copilot Chat")
                return False
            
            # 選擇 AI 模型（在聚焦輸入框之後）
            self.logger.info("🤖 選擇 AI 模型...")
            if not self.copilot_handler.select_latest_model():
                self.logger.warning("⚠️  選擇 AI 模型失敗，但繼續執行")
            
            successful_lines = 0
            failed_lines = []
            
            # 初始化本輪的回應儲存
            if round_num not in self.round_responses:
                self.round_responses[round_num] = {}
            
            for line_idx, line in enumerate(self.prompt_lines, start=1):
                # 更新 checkpoint: 記錄 Phase 1 當前處理的行數
                if self.checkpoint_manager:
                    self.checkpoint_manager.update_progress(current_line=line_idx)
                
                # 解析 prompt 行
                target_file, target_function_name = self._parse_prompt_line(line)
                if not target_file or not target_function_name:
                    self.logger.error(f"  ❌ 第 {line_idx} 行格式錯誤")
                    failed_lines.append(line_idx)
                    continue
                
                # 檢查是否應該跳過（已攻擊成功）
                function_key = f"{target_file}_{target_function_name}"
                if self.query_stats and self.query_stats.should_skip_function(function_key):
                    self.logger.info(f"  ⏭️  跳過第 {line_idx} 行（已攻擊成功）")
                    successful_lines += 1
                    continue
                
                # === 步驟 1：找出 Phase 1 開始前的行號 ===
                pre_phase1_line_number = None
                if self.function_name_tracker:
                    if round_num == 1:
                        self.logger.info(f"  🔍 搜尋原始函式 {target_function_name} 的行號...")
                        pre_phase1_line_number = self.function_name_tracker.find_original_function_line(
                            filepath=target_file,
                            original_name=target_function_name,
                            project_path=self.project_path
                        )
                        if pre_phase1_line_number:
                            self.logger.info(f"  ✅ 找到原始函式在第 {pre_phase1_line_number} 行")
                        else:
                            self.logger.warning(f"  ⚠️  未找到原始函式行號，將使用函式名稱匹配")
                    else:
                        # 第 2+ 輪：取得上一輪 Phase 1 結束後的行號
                        _, prev_line = self.function_name_tracker.get_function_name_for_round(
                            target_file, target_function_name, round_num - 1
                        )
                        pre_phase1_line_number = prev_line
                        self.logger.debug(f"  📍 第 {round_num} 輪使用上一輪的行號：{pre_phase1_line_number}")
                
                retry_count = 0
                line_success = False
                
                # === [送出 prompt 前] 讀取當前函式名稱 ===
                pre_phase1_name = target_function_name  # 預設使用原始名稱
                pre_phase1_line = pre_phase1_line_number  # 使用之前找到的行號
                
                if self.function_name_tracker and pre_phase1_line_number:
                    result = self.function_name_tracker.extract_modified_function_name_by_line(
                        filepath=target_file,
                        original_name=target_function_name,
                        line_number=pre_phase1_line_number,
                        project_path=self.project_path
                    )
                    if result:
                        pre_phase1_name, pre_phase1_line = result
                        self.logger.debug(f"  📝 [送出 prompt 前] 當前函式名稱: {pre_phase1_name} (行 {pre_phase1_line})")
                
                # 持續重試直到回應完整（最多 AS_MODE_MAX_RETRY_PER_LINE 次）
                while not line_success:
                    try:
                        # 檢查是否超過最大重試次數
                        if retry_count >= config.AS_MODE_MAX_RETRY_PER_LINE:
                            self.logger.error(f"  ❌ 第 {line_idx} 行：已達最大重試次數 ({config.AS_MODE_MAX_RETRY_PER_LINE} 次)，放棄該行")
                            failed_lines.append(line_idx)
                            break
                        
                        # 提取檔案路徑（保留完整路徑，將 / 替換為 __）
                        filename = target_file.replace('/', '__')
                        
                        if retry_count == 0:
                            self.logger.info(f"  處理第 {line_idx}/{len(self.prompt_lines)} 行: {target_file}|{target_function_name}")
                        else:
                            self.logger.info(f"  重試第 {line_idx} 行（第 {retry_count}/{config.AS_MODE_MAX_RETRY_PER_LINE} 次）")
                        
                        # 取得上一輪的回應（如果是第 2+ 輪）
                        last_response = ""
                        if round_num > 1 and (round_num - 1) in self.round_responses:
                            last_response = self.round_responses[round_num - 1].get(line_idx, "")
                            if last_response:
                                self.logger.debug(f"  📎 使用第 {round_num - 1} 輪的回應（{len(last_response)} 字元）")
                        
                        # 生成 Query Prompt
                        query_prompt = self._generate_query_prompt(
                            round_num, target_file, target_function_name, last_response
                        )
                        
                        # 發送 prompt
                        success = self.copilot_handler._send_prompt_with_content(
                            prompt_content=query_prompt,
                            line_number=line_idx,
                            total_lines=len(self.prompt_lines)
                        )
                        
                        if not success:
                            self.logger.error(f"  ❌ 第 {line_idx} 行：無法發送提示詞")
                            retry_count += 1
                            self.logger.warning(f"  ⏳ 發送失敗，等待後重試（第 {retry_count} 次）")
                            wait_and_retry(60, line_idx, round_num, self.logger, retry_count)
                            
                            # 清空輸入框準備重試
                            self._clear_input_and_refocus()
                            continue
                        
                        # 等待回應
                        if not self.copilot_handler.wait_for_response(use_smart_wait=True):
                            self.logger.error(f"  ❌ 第 {line_idx} 行：等待回應超時")
                            retry_count += 1
                            self.logger.warning(f"  ⏳ 等待超時，將重試（第 {retry_count} 次）")
                            wait_and_retry(60, line_idx, round_num, self.logger, retry_count)
                            
                            # 清空輸入框準備重試
                            self._clear_input_and_refocus()
                            continue
                        
                        # 複製回應
                        response = self.copilot_handler.copy_response()
                        if not response:
                            self.logger.error(f"  ❌ 第 {line_idx} 行：無法複製回應內容")
                            retry_count += 1
                            self.logger.warning(f"  ⏳ 複製失敗，將重試（第 {retry_count} 次）")
                            wait_and_retry(60, line_idx, round_num, self.logger, retry_count)
                            
                            # 清空輸入框準備重試
                            self._clear_input_and_refocus()
                            continue
                        
                        self.logger.info(f"  ✅ 收到回應 ({len(response)} 字元)")
                        
                        # 檢查回應完整性
                        if is_response_incomplete(response):
                            self.logger.warning(f"  ⚠️  第 {line_idx} 行回應不完整，將等待後重試")
                            retry_count += 1
                            
                            # 等待 30 分鐘後重試（無最大重試次數限制）
                            wait_and_retry(1800, line_idx, round_num, self.logger, retry_count)
                            
                            # 清空輸入框準備重試
                            self._clear_input_and_refocus()
                            
                            continue  # 繼續重試循環
                        
                        # 回應完整，儲存回應（AS 專用格式）
                        self.logger.info(f"  ✅ 第 {line_idx} 行回應完整")
                        save_success = self.copilot_handler.save_response_to_file(
                            project_path=str(self.project_path),
                            response=response,
                            is_success=True,
                            round_number=round_num,
                            phase_number=1,  # 第 1 道
                            line_number=line_idx,
                            filename=filename,
                            function_name=target_function_name,
                            prompt_text=query_prompt,
                            total_lines=len(self.prompt_lines),
                            retry_count=retry_count
                        )
                        
                        if save_success:
                            # 儲存回應供下一輪使用
                            self.round_responses[round_num][line_idx] = response
                            
                            # === [送出 prompt 後] 提取 Phase 1 結束後的函式名稱（使用行號定位）===
                            if self.function_name_tracker:
                                self.logger.info(f"  📝 [送出 prompt 後] 提取修改後的函式名稱...")
                                
                                # 使用 Phase 1 開始前的行號作為搜尋起點
                                line_to_check = pre_phase1_line if pre_phase1_line else pre_phase1_line_number
                                
                                # 如果沒有行號，嘗試重新搜尋（可能因為上一輪追蹤失敗）
                                if not line_to_check:
                                    self.logger.debug(f"  🔍 無已知行號，重新搜尋函式位置...")
                                    line_to_check = self.function_name_tracker.find_original_function_line(
                                        filepath=target_file,
                                        original_name=target_function_name,
                                        project_path=self.project_path
                                    )
                                
                                if line_to_check:
                                    # 根據行號提取新函式名稱（會在 ±30 行範圍內搜尋）
                                    result = self.function_name_tracker.extract_modified_function_name_by_line(
                                        filepath=target_file,
                                        original_name=target_function_name,
                                        line_number=line_to_check,
                                        project_path=self.project_path
                                    )
                                    
                                    if result:
                                        post_phase1_name, post_phase1_line = result
                                        
                                        # 記錄函式名稱變更 (Phase 1 = Query)
                                        # current_name: 送出 prompt 前的名稱（pre_phase1_name）
                                        # modified_name: 送出 prompt 後的名稱（post_phase1_name）
                                        self.function_name_tracker.record_function_change(
                                            filepath=target_file,
                                            original_name=target_function_name,
                                            modified_name=post_phase1_name,
                                            round_num=round_num,
                                            original_line=pre_phase1_line_number if round_num == 1 else None,  # 只有第 1 輪記錄原始行號
                                            modified_line=post_phase1_line,
                                            current_name=pre_phase1_name,  # 送出 prompt 前的名稱
                                            phase_number=1  # Phase 1 = Query
                                        )
                                        
                                        self.logger.info(f"  📝 Phase 1 記錄: {pre_phase1_name} → {post_phase1_name}（行 {pre_phase1_line} → {post_phase1_line}）")
                                        if post_phase1_name != pre_phase1_name:
                                            self.logger.info(f"  ✅ 函式名稱已變更！")
                                        else:
                                            self.logger.debug(f"  ℹ️  函式名稱未變更")
                                    else:
                                        self.logger.warning(f"  ⚠️  無法提取函式名稱（第 {line_to_check} 行附近）")
                                else:
                                    self.logger.warning(f"  ⚠️  無法定位函式行號，跳過名稱追蹤")
                            
                            successful_lines += 1
                            self.logger.info(f"  ✅ 第 {line_idx} 行處理完成" + (f"（經過 {retry_count} 次重試）" if retry_count > 0 else ""))
                            line_success = True
                        else:
                            self.logger.error(f"  ❌ 第 {line_idx} 行：儲存失敗")
                            failed_lines.append(line_idx)
                            break
                        
                        # 短暫延遲
                        if line_idx < len(self.prompt_lines):
                            time.sleep(1.5)
                        
                    except Exception as e:
                        self.logger.error(f"  ❌ 處理第 {line_idx} 行時發生錯誤: {e}")
                        failed_lines.append(line_idx)
                        break
                
                # 檢查該行是否成功完成
                if not line_success:
                    # break 退出但沒有標記失敗的情況（例如：無法複製回應、發送失敗等）
                    if line_idx not in failed_lines:
                        failed_lines.append(line_idx)
                    self.logger.warning(f"  ⚠️  第 {line_idx} 行未成功完成")
            
            # 統計結果
            if successful_lines == len(self.prompt_lines):
                self.logger.info(f"  ✅ 第 1 道完成：{successful_lines}/{len(self.prompt_lines)} 行")
                return True
            elif successful_lines > 0:
                # 部分成功也視為成功，允許繼續執行後續輪次
                self.logger.warning(f"  ⚠️  第 1 道部分完成：{successful_lines}/{len(self.prompt_lines)} 行（失敗: {failed_lines}）")
                return True
            else:
                # 全部失敗才返回 False
                self.logger.error(f"  ❌ 第 1 道全部失敗：0/{len(self.prompt_lines)} 行（失敗: {failed_lines}）")
                return False
            
        except Exception as e:
            self.logger.error(f"  ❌ 第 1 道執行錯誤: {e}")
            return False
    
    def _execute_phase2(self, round_num: int) -> bool:
        """
        執行第 2 道程序：Coding Phase + Scan
        手動處理每一行以支援 AS 專用的檔案結構
        """
        try:
            self.logger.info(f"  開始處理第 2 道程序（共 {len(self.prompt_lines)} 行）")
            
            # 開啟 Copilot Chat（應該已經開啟）
            if not self.copilot_handler.is_chat_open:
                if not self.copilot_handler.open_copilot_chat():
                    self.logger.error("  ❌ 無法開啟 Copilot Chat")
                    return False
            
            successful_lines = 0
            failed_lines = []
            
            for line_idx, line in enumerate(self.prompt_lines, start=1):
                # 更新 checkpoint: 記錄 Phase 2 當前處理的行數
                if self.checkpoint_manager:
                    self.checkpoint_manager.update_progress(current_line=line_idx)
                
                # 解析 prompt 行
                target_file, target_function_name = self._parse_prompt_line(line)
                if not target_file or not target_function_name:
                    self.logger.error(f"  ❌ 第 {line_idx} 行格式錯誤")
                    failed_lines.append(line_idx)
                    continue
                
                # === 取得 Phase 1 結束後的行號（用於讀取函式名稱）===
                phase1_end_line = None
                if self.function_name_tracker:
                    _, phase1_end_line = self.function_name_tracker.get_function_name_for_round(
                        target_file, target_function_name, round_num
                    )
                
                # 檢查是否應該跳過（已攻擊成功）
                function_key = f"{target_file}_{target_function_name}"
                if self.query_stats and self.query_stats.should_skip_function(function_key):
                    self.logger.info(f"  ⏭️  跳過第 {line_idx} 行（已攻擊成功）")
                    successful_lines += 1
                    continue
                
                # === [送出 prompt 前] 讀取當前函式名稱 ===
                pre_phase2_name = target_function_name  # 預設使用原始名稱
                pre_phase2_line = phase1_end_line
                
                if self.function_name_tracker and phase1_end_line:
                    result = self.function_name_tracker.extract_modified_function_name_by_line(
                        filepath=target_file,
                        original_name=target_function_name,
                        line_number=phase1_end_line,
                        project_path=self.project_path
                    )
                    if result:
                        pre_phase2_name, pre_phase2_line = result
                        self.logger.debug(f"  📝 [送出 prompt 前] 當前函式名稱: {pre_phase2_name} (行 {pre_phase2_line})")
                
                # 使用「送出 prompt 前」的函式名稱作為當前名稱
                current_function_name = pre_phase2_name
                
                retry_count = 0
                line_success = False
                
                # 持續重試直到回應完整（最多 AS_MODE_MAX_RETRY_PER_LINE 次）
                while not line_success:
                    try:
                        # 檢查是否超過最大重試次數
                        if retry_count >= config.AS_MODE_MAX_RETRY_PER_LINE:
                            self.logger.error(f"  ❌ 第 {line_idx} 行：已達最大重試次數 ({config.AS_MODE_MAX_RETRY_PER_LINE} 次)，放棄該行")
                            failed_lines.append(line_idx)
                            break
                        
                        # 提取檔案路徑（保留完整路徑，將 / 替換為 __）
                        filename = target_file.replace('/', '__')
                        
                        if retry_count == 0:
                            self.logger.info(f"  處理第 {line_idx}/{len(self.prompt_lines)} 行: {target_file}|{target_function_name}")
                        else:
                            self.logger.info(f"  重試第 {line_idx} 行（第 {retry_count}/{config.AS_MODE_MAX_RETRY_PER_LINE} 次）")
                        
                        # 生成 Coding Prompt
                        coding_prompt = self._generate_coding_prompt(target_file, target_function_name)
                        
                        # 發送 prompt
                        success = self.copilot_handler._send_prompt_with_content(
                            prompt_content=coding_prompt,
                            line_number=line_idx,
                            total_lines=len(self.prompt_lines)
                        )
                        
                        if not success:
                            self.logger.error(f"  ❌ 第 {line_idx} 行：無法發送提示詞")
                            retry_count += 1
                            self.logger.warning(f"  ⏳ 發送失敗，等待後重試（第 {retry_count} 次）")
                            wait_and_retry(60, line_idx, round_num, self.logger, retry_count)
                            
                            # 清空輸入框準備重試
                            self._clear_input_and_refocus()
                            continue
                        
                        # 等待回應
                        if not self.copilot_handler.wait_for_response(use_smart_wait=True):
                            self.logger.error(f"  ❌ 第 {line_idx} 行：等待回應超時")
                            retry_count += 1
                            self.logger.warning(f"  ⏳ 等待超時，將重試（第 {retry_count} 次）")
                            wait_and_retry(60, line_idx, round_num, self.logger, retry_count)
                            
                            # 清空輸入框準備重試
                            self._clear_input_and_refocus()
                            continue
                        
                        # 複製回應
                        response = self.copilot_handler.copy_response()
                        if not response:
                            self.logger.error(f"  ❌ 第 {line_idx} 行：無法複製回應內容")
                            retry_count += 1
                            self.logger.warning(f"  ⏳ 複製失敗，將重試（第 {retry_count} 次）")
                            wait_and_retry(60, line_idx, round_num, self.logger, retry_count)
                            
                            # 清空輸入框準備重試
                            self._clear_input_and_refocus()
                            continue
                        
                        self.logger.info(f"  ✅ 收到回應 ({len(response)} 字元)")
                        
                        # 檢查回應完整性
                        if is_response_incomplete(response):
                            self.logger.warning(f"  ⚠️  第 {line_idx} 行回應不完整，將等待後重試")
                            retry_count += 1
                            
                            # 等待 30 分鐘後重試（無最大重試次數限制）
                            wait_and_retry(1800, line_idx, round_num, self.logger, retry_count)
                            
                            # 清空輸入框準備重試
                            self._clear_input_and_refocus()
                            
                            continue  # 繼續重試循環
                        
                        # 回應完整，儲存回應（AS 專用格式）
                        self.logger.info(f"  ✅ 第 {line_idx} 行回應完整")
                        save_success = self.copilot_handler.save_response_to_file(
                            project_path=str(self.project_path),
                            response=response,
                            is_success=True,
                            round_number=round_num,
                            phase_number=2,  # 第 2 道
                            line_number=line_idx,
                            filename=filename,
                            function_name=current_function_name,  # 使用修改後的函式名稱
                            prompt_text=coding_prompt,
                            total_lines=len(self.prompt_lines),
                            retry_count=retry_count
                        )
                        
                        if not save_success:
                            self.logger.error(f"  ❌ 第 {line_idx} 行：儲存失敗")
                            failed_lines.append(line_idx)
                            break
                        
                        # === CWE 掃描 + [送出 prompt 後] Phase 2 函式名稱追蹤 ===
                        self.logger.info(f"  🔍 開始掃描第 {line_idx} 行的函式")
                        
                        # === [送出 prompt 後] 讀取 Phase 2 結束後的函式名稱 ===
                        post_phase2_name = pre_phase2_name  # 預設使用「送出 prompt 前」的名稱
                        post_phase2_line = pre_phase2_line
                        
                        if self.function_name_tracker and pre_phase2_line:
                            # 從檔案中讀取 Phase 2 結束後的函式名稱
                            result = self.function_name_tracker.extract_modified_function_name_by_line(
                                filepath=target_file,
                                original_name=target_function_name,
                                line_number=pre_phase2_line,
                                project_path=self.project_path
                            )
                            
                            if result:
                                post_phase2_name, post_phase2_line = result
                                
                                # 記錄 Phase 2 (Coding) 的函式名稱（無論是否變更）
                                # current_name: 送出 prompt 前的名稱（pre_phase2_name）
                                # modified_name: 送出 prompt 後的名稱（post_phase2_name）
                                self.function_name_tracker.record_function_change(
                                    filepath=target_file,
                                    original_name=target_function_name,  # 原始名稱（prompt.txt 中的名稱）
                                    modified_name=post_phase2_name,       # 送出 prompt 後的名稱
                                    round_num=round_num,
                                    original_line=None,  # Phase 2 不記錄原始行號
                                    modified_line=post_phase2_line,
                                    current_name=pre_phase2_name,         # 送出 prompt 前的名稱
                                    phase_number=2  # Phase 2 = Coding
                                )
                                
                                self.logger.info(f"  📝 Phase 2 記錄: {pre_phase2_name} → {post_phase2_name}（行 {pre_phase2_line} → {post_phase2_line}）")
                                if post_phase2_name != pre_phase2_name:
                                    self.logger.info(f"  ✅ 函式名稱已變更！")
                                else:
                                    self.logger.debug(f"  ℹ️  函式名稱未變更")
                            else:
                                self.logger.warning(f"  ⚠️  無法提取 Phase 2 結束後的函式名稱")
                        elif not pre_phase2_line:
                            self.logger.warning(f"  ⚠️  無法取得 Phase 2 開始前的行號")
                        
                        if self.cwe_scan_manager:
                            try:
                                # 構造只包含當前處理函數的 prompt
                                # 格式: filepath|function_name (使用 Phase 2 結束後的名稱)
                                single_function_prompt = f"{target_file}|{post_phase2_name}"
                                
                                # 呼叫函式級別掃描（會自動追加到 CSV）
                                # - original_function_name: prompt.txt 中的原始名稱（用於 CSV「修改前函式名稱」）
                                # - modified_function_name: Phase 1 修改後的名稱（用於 CSV「修改後函式名稱」）
                                # - actual_function_name: Phase 2 後的名稱（用於實際掃描）
                                scan_success, scan_files, vuln_info = self.cwe_scan_manager.scan_from_prompt_function_level(
                                    project_path=self.project_path,
                                    project_name=self.project_path.name,
                                    prompt_content=single_function_prompt,  # 只掃描實際處理的函數
                                    cwe_type=self.target_cwe,
                                    round_number=round_num,
                                    line_number=line_idx,
                                    original_function_name=target_function_name,  # prompt.txt 中的原始名稱
                                    modified_function_name=current_function_name   # Phase 1 修改後的名稱
                                )
                                
                                if scan_success:
                                    self.logger.info(f"  ✅ 掃描完成")
                                    # 記錄漏洞資訊到 vicious_pattern_manager（用於後續備份 vicious pattern）
                                    # 注意：使用 current_function_name（Phase 1 修改後的名稱）而不是掃描返回的名稱
                                    # 因為我們要記錄的是「容易被製造漏洞的函式名稱」
                                    if vuln_info and self.vicious_pattern_manager:
                                        for file_path, func_list in vuln_info.items():
                                            for func_name, vuln_count in func_list:
                                                self.vicious_pattern_manager.add_vulnerable_function(
                                                    file_path=file_path,
                                                    function_name=current_function_name,  # 使用 Phase 1 修改後的名稱
                                                    round_number=round_num,
                                                    vulnerability_count=vuln_count,
                                                    scanner="combined"
                                                )
                                                self.logger.info(f"    📌 記錄漏洞: {file_path}::{current_function_name} ({vuln_count} 個)")
                                else:
                                    self.logger.warning(f"  ⚠️  掃描未找到目標函式")
                            except Exception as e:
                                self.logger.error(f"  ❌ 掃描時發生錯誤: {e}")
                        else:
                            self.logger.warning("  ⚠️  CWE scan manager 未提供，跳過掃描")
                        
                        successful_lines += 1
                        self.logger.info(f"  ✅ 第 {line_idx} 行處理完成" + (f"（經過 {retry_count} 次重試）" if retry_count > 0 else ""))
                        line_success = True
                        
                        # 短暫延遲
                        if line_idx < len(self.prompt_lines):
                            time.sleep(1.5)
                        
                    except Exception as e:
                        self.logger.error(f"  ❌ 處理第 {line_idx} 行時發生錯誤: {e}")
                        failed_lines.append(line_idx)
                        break
                
                # 檢查該行是否成功完成
                if not line_success:
                    # break 退出但沒有標記失敗的情況（例如：無法複製回應、發送失敗等）
                    if line_idx not in failed_lines:
                        failed_lines.append(line_idx)
                    self.logger.warning(f"  ⚠️  第 {line_idx} 行未成功完成")
            
            # 統計結果
            if successful_lines == len(self.prompt_lines):
                self.logger.info(f"  ✅ 第 2 道完成：{successful_lines}/{len(self.prompt_lines)} 行")
                return True
            elif successful_lines > 0:
                # 部分成功也視為成功，允許繼續執行後續輪次
                self.logger.warning(f"  ⚠️  第 2 道部分完成：{successful_lines}/{len(self.prompt_lines)} 行（失敗: {failed_lines}）")
                return True
            else:
                # 全部失敗才返回 False
                self.logger.error(f"  ❌ 第 2 道全部失敗：0/{len(self.prompt_lines)} 行（失敗: {failed_lines}）")
                return False
            
        except Exception as e:
            self.logger.error(f"  ❌ 第 2 道執行錯誤: {e}")
            return False
