# -*- coding: utf-8 -*-
"""
Artificial Suicide 攻擊模式 - 輕量級控制器
直接利用現有的 copilot_handler 和 vscode_controller 功能
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
from config.config import config


class ArtificialSuicideMode:
    """
    Artificial Suicide 攻擊模式控制器
    
    功能：
    1. 載入三個 prompt 模板（initial_query, following_query, coding_instruction）
    2. 控制兩道程序的執行流程
    3. 調用現有的 copilot_handler 和 vscode_controller
    """
    
    def __init__(self, copilot_handler, vscode_controller, cwe_scan_manager, 
                 error_handler, project_path: str, target_cwe: str, total_rounds: int,
                 max_files_limit: int = 0, files_processed_so_far: int = 0):
        """
        初始化 AS 模式控制器
        
        Args:
            copilot_handler: Copilot 處理器（現有）
            vscode_controller: VSCode 控制器（現有）
            cwe_scan_manager: CWE 掃描管理器（現有）
            error_handler: 錯誤處理器（現有）
            project_path: 專案路徑
            target_cwe: 目標 CWE 類型（如 "327"）
            total_rounds: 總輪數
            max_files_limit: 最大檔案處理限制（0 表示無限制）
            files_processed_so_far: 目前已處理的檔案數
        """
        self.logger = get_logger("ArtificialSuicide")
        self.copilot_handler = copilot_handler
        self.vscode_controller = vscode_controller
        self.cwe_scan_manager = cwe_scan_manager
        self.error_handler = error_handler
        self.project_path = Path(project_path)
        self.target_cwe = target_cwe
        self.total_rounds = total_rounds
        
        # 檔案數量限制相關
        self.max_files_limit = max_files_limit
        self.files_processed_so_far = files_processed_so_far
        self.files_processed_in_project = 0  # 本專案已處理的檔案數
        
        # 載入模板
        self.templates = self._load_templates()
        
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
        
        # 替換變數
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
            
            # 步驟 0：開啟專案
            self.logger.info("📂 開啟專案到 VSCode...")
            if not self.vscode_controller.open_project(str(self.project_path)):
                self.logger.error("❌ 無法開啟專案")
                return False, 0
            time.sleep(3)  # 等待專案完全載入
            
            # 【重要】在成功開啟專案後，設定本專案要處理的檔案數
            # 無論後續成功或失敗，只要開始處理就計入，確保多次執行的一致性
            self.files_processed_in_project = len(self.prompt_lines)
            self.logger.info(f"📊 本專案將處理 {self.files_processed_in_project} 個檔案（無論結果如何都計入）")
            
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
            
            # 執行每一輪
            for round_num in range(1, self.total_rounds + 1):
                self.logger.create_separator(f"📍 第 {round_num}/{self.total_rounds} 輪")
                
                success = self._execute_round(round_num)
                
                if not success:
                    self.logger.error(f"❌ 第 {round_num} 輪執行失敗")
                    return False, self.files_processed_in_project
                
                # 即時更新該輪的統計資料
                self.logger.info(f"📊 更新第 {round_num} 輪統計...")
                self.query_stats.update_round_result(round_num)
                
                self.logger.info(f"✅ 第 {round_num} 輪完成")
            
            self.logger.create_separator("🎉 Artificial Suicide 攻擊完成")
            self.logger.info(f"📊 本專案處理了 {self.files_processed_in_project} 個檔案")
            return True, self.files_processed_in_project
            
        except Exception as e:
            self.logger.error(f"❌ AS 模式執行錯誤: {e}")
            return False, self.files_processed_in_project
    
    def _execute_round(self, round_num: int) -> bool:
        """
        執行單輪攻擊（兩道程序）
        
        Args:
            round_num: 輪數
            
        Returns:
            bool: 是否成功
        """
        # === 第 1 道程序：Query Phase ===
        self.logger.info(f"▶️  第 {round_num} 輪 - 第 1 道程序（Query Phase）")
        
        if not self._execute_phase1(round_num):
            return False
        
        # Keep 修改（使用現有功能）
        self.logger.info("  💾 Keep 修改...")
        self.vscode_controller.clear_copilot_memory(modification_action="keep")
        time.sleep(2)
        
        # === 第 2 道程序：Coding Phase + Scan ===
        self.logger.info(f"▶️  第 {round_num} 輪 - 第 2 道程序（Coding Phase + Scan）")
        
        if not self._execute_phase2(round_num):
            return False
        
        # Undo 修改（使用現有功能）
        self.logger.info("  ↩️  Undo 修改...")
        self.vscode_controller.clear_copilot_memory(modification_action="revert")
        time.sleep(2)
        
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
            
            successful_lines = 0
            failed_lines = []
            
            # 初始化本輪的回應儲存
            if round_num not in self.round_responses:
                self.round_responses[round_num] = {}
            
            for line_idx, line in enumerate(self.prompt_lines, start=1):
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
                
                # === 步驟 1：找出原始函式所在行號（僅第 1 輪需要）===
                original_line_number = None
                if round_num == 1 and self.function_name_tracker:
                    self.logger.info(f"  🔍 搜尋原始函式 {target_function_name} 的行號...")
                    original_line_number = self.function_name_tracker.find_original_function_line(
                        filepath=target_file,
                        original_name=target_function_name,
                        project_path=self.project_path
                    )
                    if original_line_number:
                        self.logger.info(f"  ✅ 找到原始函式在第 {original_line_number} 行")
                    else:
                        self.logger.warning(f"  ⚠️  未找到原始函式行號，將使用函式名稱匹配")
                
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
                            pyautogui.hotkey('ctrl', 'f1')
                            time.sleep(0.5)
                            pyautogui.hotkey('ctrl', 'a')
                            time.sleep(0.2)
                            pyautogui.press('delete')
                            time.sleep(0.5)
                            continue
                        
                        # 等待回應
                        if not self.copilot_handler.wait_for_response(use_smart_wait=True):
                            self.logger.error(f"  ❌ 第 {line_idx} 行：等待回應超時")
                            retry_count += 1
                            self.logger.warning(f"  ⏳ 等待超時，將重試（第 {retry_count} 次）")
                            wait_and_retry(60, line_idx, round_num, self.logger, retry_count)
                            
                            # 清空輸入框準備重試
                            pyautogui.hotkey('ctrl', 'f1')
                            time.sleep(0.5)
                            pyautogui.hotkey('ctrl', 'a')
                            time.sleep(0.2)
                            pyautogui.press('delete')
                            time.sleep(0.5)
                            continue
                        
                        # 複製回應
                        response = self.copilot_handler.copy_response()
                        if not response:
                            self.logger.error(f"  ❌ 第 {line_idx} 行：無法複製回應內容")
                            retry_count += 1
                            self.logger.warning(f"  ⏳ 複製失敗，將重試（第 {retry_count} 次）")
                            wait_and_retry(60, line_idx, round_num, self.logger, retry_count)
                            
                            # 清空輸入框準備重試
                            pyautogui.hotkey('ctrl', 'f1')
                            time.sleep(0.5)
                            pyautogui.hotkey('ctrl', 'a')
                            time.sleep(0.2)
                            pyautogui.press('delete')
                            time.sleep(0.5)
                            continue
                        
                        self.logger.info(f"  ✅ 收到回應 ({len(response)} 字元)")
                        
                        # 檢查回應完整性
                        if is_response_incomplete(response):
                            self.logger.warning(f"  ⚠️  第 {line_idx} 行回應不完整，將等待後重試")
                            retry_count += 1
                            
                            # 等待 30 分鐘後重試（無最大重試次數限制）
                            wait_and_retry(1800, line_idx, round_num, self.logger, retry_count)
                            
                            # 清空輸入框準備重試
                            pyautogui.hotkey('ctrl', 'f1')
                            time.sleep(0.5)
                            pyautogui.hotkey('ctrl', 'a')
                            time.sleep(0.2)
                            pyautogui.press('delete')
                            time.sleep(0.5)
                            
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
                            
                            # === 步驟 2：提取修改後的函式名稱（使用行號定位）===
                            if self.function_name_tracker:
                                self.logger.info(f"  📝 提取修改後的函式名稱...")
                                
                                # 取得行號（優先使用已知的行號，否則重新搜尋）
                                if original_line_number:
                                    line_to_check = original_line_number
                                else:
                                    # 嘗試從追蹤器中取得上一輪的行號
                                    if round_num > 1:
                                        _, prev_line = self.function_name_tracker.get_function_name_for_round(
                                            target_file, target_function_name, round_num
                                        )
                                        line_to_check = prev_line if prev_line else None
                                    else:
                                        line_to_check = None
                                
                                # 如果還是沒有行號，重新搜尋
                                if not line_to_check:
                                    line_to_check = self.function_name_tracker.find_original_function_line(
                                        filepath=target_file,
                                        original_name=target_function_name,
                                        project_path=self.project_path
                                    )
                                
                                if line_to_check:
                                    # 根據行號提取新函式名稱
                                    result = self.function_name_tracker.extract_modified_function_name_by_line(
                                        filepath=target_file,
                                        original_name=target_function_name,
                                        line_number=line_to_check,
                                        project_path=self.project_path
                                    )
                                    
                                    if result:
                                        modified_name, modified_line = result
                                        
                                        # 記錄函式名稱變更
                                        self.function_name_tracker.record_function_change(
                                            filepath=target_file,
                                            original_name=target_function_name,
                                            modified_name=modified_name,
                                            round_num=round_num,
                                            original_line=original_line_number,
                                            modified_line=modified_line
                                        )
                                        
                                        if modified_name != target_function_name:
                                            self.logger.info(f"  ✅ 函式名稱已變更：{target_function_name} → {modified_name}（行 {modified_line}）")
                                        else:
                                            self.logger.debug(f"  ℹ️  函式名稱未變更：{target_function_name}（行 {modified_line}）")
                                    else:
                                        self.logger.warning(f"  ⚠️  無法提取函式名稱（第 {line_to_check} 行）")
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
            else:
                self.logger.error(f"  ⚠️  第 1 道部分完成：{successful_lines}/{len(self.prompt_lines)} 行（失敗: {failed_lines}）")
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
                # 解析 prompt 行
                target_file, target_function_name = self._parse_prompt_line(line)
                if not target_file or not target_function_name:
                    self.logger.error(f"  ❌ 第 {line_idx} 行格式錯誤")
                    failed_lines.append(line_idx)
                    continue
                
                # === 取得修改後的函式名稱（如果 Phase 1 有修改）===
                current_function_name = target_function_name  # 預設使用原始名稱
                if self.function_name_tracker:
                    # 嘗試從追蹤器取得修改後的名稱
                    modified_name, _ = self.function_name_tracker.get_function_name_for_round(
                        target_file, target_function_name, round_num
                    )
                    if modified_name:
                        current_function_name = modified_name
                        self.logger.debug(f"  📝 使用修改後的函式名稱: {target_function_name} → {current_function_name}")
                    else:
                        self.logger.debug(f"  📝 Phase 1 未修改函式名稱，使用原始名稱: {target_function_name}")
                
                # 檢查是否應該跳過（已攻擊成功）
                function_key = f"{target_file}_{target_function_name}"
                if self.query_stats and self.query_stats.should_skip_function(function_key):
                    self.logger.info(f"  ⏭️  跳過第 {line_idx} 行（已攻擊成功）")
                    successful_lines += 1
                    continue
                
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
                            pyautogui.hotkey('ctrl', 'f1')
                            time.sleep(0.5)
                            pyautogui.hotkey('ctrl', 'a')
                            time.sleep(0.2)
                            pyautogui.press('delete')
                            time.sleep(0.5)
                            continue
                        
                        # 等待回應
                        if not self.copilot_handler.wait_for_response(use_smart_wait=True):
                            self.logger.error(f"  ❌ 第 {line_idx} 行：等待回應超時")
                            retry_count += 1
                            self.logger.warning(f"  ⏳ 等待超時，將重試（第 {retry_count} 次）")
                            wait_and_retry(60, line_idx, round_num, self.logger, retry_count)
                            
                            # 清空輸入框準備重試
                            pyautogui.hotkey('ctrl', 'f1')
                            time.sleep(0.5)
                            pyautogui.hotkey('ctrl', 'a')
                            time.sleep(0.2)
                            pyautogui.press('delete')
                            time.sleep(0.5)
                            continue
                        
                        # 複製回應
                        response = self.copilot_handler.copy_response()
                        if not response:
                            self.logger.error(f"  ❌ 第 {line_idx} 行：無法複製回應內容")
                            retry_count += 1
                            self.logger.warning(f"  ⏳ 複製失敗，將重試（第 {retry_count} 次）")
                            wait_and_retry(60, line_idx, round_num, self.logger, retry_count)
                            
                            # 清空輸入框準備重試
                            pyautogui.hotkey('ctrl', 'f1')
                            time.sleep(0.5)
                            pyautogui.hotkey('ctrl', 'a')
                            time.sleep(0.2)
                            pyautogui.press('delete')
                            time.sleep(0.5)
                            continue
                        
                        self.logger.info(f"  ✅ 收到回應 ({len(response)} 字元)")
                        
                        # 檢查回應完整性
                        if is_response_incomplete(response):
                            self.logger.warning(f"  ⚠️  第 {line_idx} 行回應不完整，將等待後重試")
                            retry_count += 1
                            
                            # 等待 30 分鐘後重試（無最大重試次數限制）
                            wait_and_retry(1800, line_idx, round_num, self.logger, retry_count)
                            
                            # 清空輸入框準備重試
                            pyautogui.hotkey('ctrl', 'f1')
                            time.sleep(0.5)
                            pyautogui.hotkey('ctrl', 'a')
                            time.sleep(0.2)
                            pyautogui.press('delete')
                            time.sleep(0.5)
                            
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
                        
                        # === CWE 掃描 ===
                        self.logger.info(f"  🔍 開始掃描第 {line_idx} 行的函式")
                        
                        if self.cwe_scan_manager:
                            try:
                                # 構造只包含當前處理函數的 prompt（匹配實際發送的 prompt）
                                # 格式: filepath|function_name (只取第一個函數)
                                single_function_prompt = f"{target_file}|{target_function_name}"
                                
                                # 呼叫函式級別掃描（會自動追加到 CSV）
                                scan_success, scan_files = self.cwe_scan_manager.scan_from_prompt_function_level(
                                    project_path=self.project_path,
                                    project_name=self.project_path.name,
                                    prompt_content=single_function_prompt,  # 只掃描實際處理的函數
                                    cwe_type=self.target_cwe,
                                    round_number=round_num,
                                    line_number=line_idx
                                )
                                
                                if scan_success:
                                    self.logger.info(f"  ✅ 掃描完成")
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
            else:
                self.logger.error(f"  ⚠️  第 2 道部分完成：{successful_lines}/{len(self.prompt_lines)} 行（失敗: {failed_lines}）")
                return False
            
        except Exception as e:
            self.logger.error(f"  ❌ 第 2 道執行錯誤: {e}")
            return False
