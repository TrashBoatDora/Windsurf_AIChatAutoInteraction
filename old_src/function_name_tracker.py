# -*- coding: utf-8 -*-
"""
Function Name Tracker - 追蹤 AI 修改後的函式名稱
用於記錄每一輪 Query Phase 中，AI 將原始函式名稱修改成什麼

目的：
在 Artificial Suicide 模式中，第一道程序會要求 AI 修改函式名稱，
但後續輪次需要使用修改後的名稱來生成 Coding Prompt。
此模組負責：
1. 解析 AI 回應或專案檔案，提取新的函式名稱
2. 儲存到 FunctionName_query.csv
3. 提供查詢接口，讓後續輪次可以取得最新的函式名稱
"""

import csv
import re
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime

from src.logger import get_logger


class FunctionNameTracker:
    """
    函式名稱追蹤器
    
    管理 FunctionName_query.csv 文件，記錄每輪的函式名稱變更
    """
    
    def __init__(self, project_name: str, execution_result_path: Path = None):
        """
        初始化追蹤器
        
        Args:
            project_name: 專案名稱
            execution_result_path: ExecutionResult 基礎路徑（預設為專案根目錄/ExecutionResult）
        """
        self.logger = get_logger("FunctionNameTracker")
        self.project_name = project_name
        
        # 設定基礎路徑
        if execution_result_path is None:
            self.execution_result_path = Path(__file__).parent.parent / "ExecutionResult"
        else:
            self.execution_result_path = execution_result_path
        
        # CSV 資料夾路徑：ExecutionResult/Success/{project}/FunctionName_query/
        self.csv_dir = self.execution_result_path / "Success" / project_name / "FunctionName_query"
        
        # 內存中的函式名稱映射：{(filepath, original_name): [(round, modified_name, line_number), ...]}
        self.function_mapping: Dict[Tuple[str, str], list] = {}
        
        # 內存中的原始函式行號映射：{(filepath, original_name): line_number}
        self.original_line_numbers: Dict[Tuple[str, str], int] = {}
        
        self.logger.info(f"初始化函式名稱追蹤器 - 專案: {project_name}")
    
    def initialize_csv(self) -> bool:
        """
        初始化 CSV 資料夾
        
        Returns:
            bool: 是否成功初始化
        """
        try:
            # 確保資料夾存在
            self.csv_dir.mkdir(parents=True, exist_ok=True)
            
            # 載入所有現有的輪次資料
            if self.csv_dir.exists():
                self._load_all_rounds()
            
            self.logger.info(f"✅ 初始化 CSV 資料夾: {self.csv_dir}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 初始化 CSV 資料夾時發生錯誤: {e}")
            return False
    
    def _load_all_rounds(self) -> bool:
        """
        載入所有輪次的 CSV 資料到內存
        
        Returns:
            bool: 是否成功載入
        """
        try:
            loaded_count = 0
            
            # 尋找所有 roundN.csv 檔案
            for csv_file in sorted(self.csv_dir.glob("round*.csv")):
                try:
                    with open(csv_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            filepath = row.get('檔案路徑', '').strip()
                            original_name = row.get('原始函式名稱', '').strip()
                            original_line = row.get('原始行號', '').strip()
                            round_num = row.get('輪數', '').strip()
                            # 兼容新舊欄位名稱
                            modified_name = row.get('當前函式名稱', '').strip() or row.get('修改後函式名稱', '').strip()
                            modified_line = row.get('修改後行號', '').strip()
                            
                            if not filepath or not original_name or not round_num or not modified_name:
                                continue
                            
                            key = (filepath, original_name)
                            if key not in self.function_mapping:
                                self.function_mapping[key] = []
                            
                            # 儲存原始行號
                            if original_line and key not in self.original_line_numbers:
                                self.original_line_numbers[key] = int(original_line)
                            
                            # 儲存修改記錄（包含行號）
                            line_num = int(modified_line) if modified_line else None
                            self.function_mapping[key].append((int(round_num), modified_name, line_num))
                            loaded_count += 1
                    
                    self.logger.debug(f"載入 {csv_file.name}")
                except Exception as e:
                    self.logger.error(f"載入 {csv_file.name} 時發生錯誤: {e}")
            
            if loaded_count > 0:
                self.logger.info(f"✅ 載入現有資料：{len(self.function_mapping)} 個函式，共 {loaded_count} 筆記錄")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 載入現有資料時發生錯誤: {e}")
            return False
    
    def find_original_function_line(self, filepath: str, original_name: str, 
                                   project_path: Path) -> Optional[int]:
        """
        找出原始函式所在的行號
        
        Args:
            filepath: 檔案相對路徑
            original_name: 原始函式名稱（如 generate_fernet_key()）
            project_path: 專案根目錄路徑
            
        Returns:
            行號（1-based）或 None
        """
        try:
            # 移除括號
            original_name_clean = original_name.replace('()', '').strip()
            
            # 完整檔案路徑
            full_path = project_path / filepath
            
            if not full_path.exists():
                self.logger.warning(f"⚠️  檔案不存在: {full_path}")
                return None
            
            # 逐行讀取檔案
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 搜尋函式定義：def original_name(
            pattern = rf'def\s+{re.escape(original_name_clean)}\s*\('
            
            for line_num, line in enumerate(lines, start=1):
                if re.search(pattern, line):
                    self.logger.info(f"✅ 找到原始函式 {original_name} 在第 {line_num} 行")
                    
                    # 儲存到內存
                    key = (filepath, original_name)
                    self.original_line_numbers[key] = line_num
                    
                    return line_num
            
            self.logger.warning(f"⚠️  未找到原始函式 {original_name} 的定義")
            return None
            
        except Exception as e:
            self.logger.error(f"❌ 搜尋函式行號時發生錯誤: {e}")
            return None
    
    def extract_modified_function_name_by_line(self, filepath: str, original_name: str,
                                               line_number: int, project_path: Path) -> Optional[Tuple[str, int]]:
        """
        根據行號提取修改後的函式名稱
        
        Args:
            filepath: 檔案相對路徑
            original_name: 原始函式名稱（用於日誌）
            line_number: 原始函式所在行號
            project_path: 專案根目錄路徑
            
        Returns:
            (修改後的函式名稱, 新行號) 或 None
        """
        try:
            # 完整檔案路徑
            full_path = project_path / filepath
            
            if not full_path.exists():
                self.logger.warning(f"⚠️  檔案不存在: {full_path}")
                return None
            
            # 讀取檔案
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 檢查行號是否有效
            if line_number < 1 or line_number > len(lines):
                self.logger.warning(f"⚠️  行號 {line_number} 超出範圍（檔案共 {len(lines)} 行）")
                return None
            
            # 讀取該行內容（注意：list 是 0-based）
            target_line = lines[line_number - 1]
            
            # 提取函式名稱：def function_name(
            pattern = r'def\s+(\w+)\s*\('
            match = re.search(pattern, target_line)
            
            if match:
                modified_name = match.group(1) + '()'
                
                # 移除括號比較
                original_name_clean = original_name.replace('()', '').strip()
                modified_name_clean = modified_name.replace('()', '').strip()
                
                if modified_name_clean != original_name_clean:
                    self.logger.info(f"✅ 提取修改後函式名稱: {original_name} → {modified_name}（第 {line_number} 行）")
                    return (modified_name, line_number)
                else:
                    self.logger.debug(f"函式名稱未修改: {original_name}（第 {line_number} 行）")
                    return (original_name, line_number)
            else:
                self.logger.warning(f"⚠️  第 {line_number} 行無法解析函式定義: {target_line.strip()}")
                return None
            
        except Exception as e:
            self.logger.error(f"❌ 提取函式名稱時發生錯誤: {e}")
            return None
    
    def record_function_change(self, filepath: str, original_name: str, 
                              modified_name: str, round_num: int,
                              original_line: int = None, modified_line: int = None,
                              current_name: str = None) -> bool:
        """
        記錄函式名稱變更到該輪次的 CSV
        
        Args:
            filepath: 檔案路徑
            original_name: 原始函式名稱（從 prompt.txt 讀取）
            modified_name: 修改後函式名稱（AI 修改後的新名稱）
            round_num: 輪數
            original_line: 原始行號
            modified_line: 修改後行號
            current_name: 當前函式名稱（送出 prompt 前的名稱，若為 None 則自動推斷）
            
        Returns:
            bool: 是否成功記錄
        """
        try:
            # 更新內存映射
            key = (filepath, original_name)
            if key not in self.function_mapping:
                self.function_mapping[key] = []
            
            # 檢查是否已記錄該輪次
            existing_rounds = [r for r, _, _ in self.function_mapping[key]]
            if round_num in existing_rounds:
                self.logger.warning(f"⚠️  第 {round_num} 輪已記錄過：{filepath} | {original_name}")
                return True
            
            # 添加新記錄（包含行號）
            self.function_mapping[key].append((round_num, modified_name, modified_line))
            
            # 儲存原始行號
            if original_line and key not in self.original_line_numbers:
                self.original_line_numbers[key] = original_line
            
            # 推斷當前函式名稱（送出 prompt 前的名稱）
            if current_name is None:
                if round_num == 1:
                    # 第 1 輪的當前名稱就是原始名稱
                    current_name = original_name
                else:
                    # 第 N 輪的當前名稱是第 N-1 輪的修改後名稱
                    prev_name, _ = self.get_function_name_for_round(filepath, original_name, round_num)
                    current_name = prev_name
            
            # 寫入到該輪次的 CSV
            round_csv_path = self.csv_dir / f"round{round_num}.csv"
            
            # 準備表頭（新格式：輪數、原始行號、檔案路徑、原始函式名稱、當前函式名稱、修改後函式名稱、修改後行號、時間戳記）
            headers = ['輪數', '原始行號', '檔案路徑', '原始函式名稱', '當前函式名稱', '修改後函式名稱', '修改後行號', '時間戳記']
            
            # 如果檔案不存在，先寫入表頭
            file_exists = round_csv_path.exists()
            
            with open(round_csv_path, 'a', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                
                if not file_exists:
                    writer.writerow(headers)
                
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                writer.writerow([
                    round_num,
                    original_line if original_line else '',
                    filepath, 
                    original_name,
                    current_name,
                    modified_name,
                    modified_line if modified_line else '',
                    timestamp
                ])
            
            self.logger.info(f"✅ 記錄函式變更：第 {round_num} 輪 - {current_name} → {modified_name}（原始: {original_name}，行 {modified_line}）")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 記錄函式變更時發生錯誤: {e}")
            return False
    
    def get_latest_function_name(self, filepath: str, original_name: str) -> Tuple[str, Optional[int]]:
        """
        取得最新的函式名稱和行號
        
        Args:
            filepath: 檔案路徑
            original_name: 原始函式名稱
            
        Returns:
            (最新的函式名稱, 行號)（如果沒有變更則返回原始名稱和原始行號）
        """
        key = (filepath, original_name)
        
        if key not in self.function_mapping or not self.function_mapping[key]:
            # 沒有記錄，返回原始名稱和原始行號
            original_line = self.original_line_numbers.get(key)
            return (original_name, original_line)
        
        # 找出最新輪次的名稱
        sorted_records = sorted(self.function_mapping[key], key=lambda x: x[0], reverse=True)
        latest_round, latest_name, latest_line = sorted_records[0]
        
        self.logger.debug(f"取得最新函式名稱：{original_name} → {latest_name}（第 {latest_round} 輪，行 {latest_line}）")
        return (latest_name, latest_line)
    
    def get_function_name_for_round(self, filepath: str, original_name: str, 
                                    target_round: int) -> Tuple[str, Optional[int]]:
        """
        取得指定輪次應該使用的函式名稱和行號
        
        邏輯：
        - 第 1 輪：使用原始名稱和原始行號
        - 第 N 輪（N > 1）：使用第 N-1 輪修改後的名稱和行號
        
        Args:
            filepath: 檔案路徑
            original_name: 原始函式名稱
            target_round: 目標輪次
            
        Returns:
            (該輪次應使用的函式名稱, 行號)
        """
        key = (filepath, original_name)
        
        if target_round == 1:
            # 第 1 輪使用原始名稱和原始行號
            original_line = self.original_line_numbers.get(key)
            return (original_name, original_line)
        
        if key not in self.function_mapping or not self.function_mapping[key]:
            # 沒有變更記錄，使用原始名稱和原始行號
            original_line = self.original_line_numbers.get(key)
            return (original_name, original_line)
        
        # 找出 < target_round 的最新記錄
        valid_records = [(r, name, line) for r, name, line in self.function_mapping[key] 
                        if r < target_round]
        
        if not valid_records:
            # 沒有之前的記錄，使用原始名稱和原始行號
            original_line = self.original_line_numbers.get(key)
            return (original_name, original_line)
        
        # 取最新的記錄
        sorted_records = sorted(valid_records, key=lambda x: x[0], reverse=True)
        _, latest_name, latest_line = sorted_records[0]
        
        self.logger.debug(f"第 {target_round} 輪使用函式名稱：{latest_name}（行 {latest_line}）")
        return (latest_name, latest_line)


def create_function_name_tracker(project_name: str, 
                                 execution_result_path: Path = None) -> FunctionNameTracker:
    """
    便捷函式：建立函式名稱追蹤器並初始化 CSV
    
    Args:
        project_name: 專案名稱
        execution_result_path: ExecutionResult 基礎路徑（可選）
        
    Returns:
        FunctionNameTracker: 追蹤器實例
    """
    tracker = FunctionNameTracker(project_name, execution_result_path)
    tracker.initialize_csv()
    return tracker
