# -*- coding: utf-8 -*-
"""
CWE 掃描結果管理模組
負責：
1. 解析 prompt 提取要掃描的檔案
2. 執行 Bandit CWE 掃描
3. 將結果儲存為 CSV 格式
4. 維護專案統計資料
"""

import re
import csv
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass
from datetime import datetime

from src.logger import get_logger
from src.cwe_detector import CWEDetector, CWEVulnerability
from src.function_name_tracker import FunctionNameTracker

logger = get_logger("CWEScanManager")


@dataclass
class ScanResult:
    """單一檔案的掃描結果"""
    file_path: str
    has_vulnerability: bool
    vulnerability_count: int = 0
    details: List[CWEVulnerability] = None


@dataclass
class FunctionTarget:
    """函式目標 - 從 prompt 提取的函式資訊"""
    file_path: str
    function_names: List[str]  # 可能有多個函式
    
    def get_function_keys(self) -> List[str]:
        """獲取函式鍵值列表（檔案名_函式名）"""
        return [f"{self.file_path}_{fn}()" for fn in self.function_names]


class CWEScanManager:
    """CWE 掃描結果管理器"""
    
    def __init__(self, output_dir: Path = None, function_name_tracker: FunctionNameTracker = None):
        """
        初始化掃描管理器
        
        Args:
            output_dir: 輸出目錄，預設為 ./CWE_Result
            function_name_tracker: 函式名稱追蹤器（用於記錄修改前/後的函式名稱）
        """
        self.output_dir = output_dir or Path("./CWE_Result")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.detector = CWEDetector()
        self.function_name_tracker = function_name_tracker
        self.logger = get_logger("CWEScanManager")
        self.logger.info(f"CWE 掃描管理器初始化完成，輸出目錄: {self.output_dir}")
    
    def extract_file_paths_from_prompt(self, prompt_content: str) -> List[str]:
        """
        從 prompt 內容中提取檔案路徑，格式為每行: {檔案}|{函式}
        Args:
            prompt_content: prompt 內容（多行）
        Returns:
            List[str]: 提取到的檔案路徑列表
        """
        file_paths = []
        seen_paths = set()
        for line in prompt_content.strip().splitlines():
            parts = line.strip().split('|')
            if len(parts) == 2:
                file_path = parts[0].strip()
                if file_path and file_path not in seen_paths:
                    file_paths.append(file_path)
                    seen_paths.add(file_path)
        self.logger.info(f"從 prompt 中提取到 {len(file_paths)} 個檔案路徑")
        for path in file_paths:
            self.logger.debug(f"  - {path}")
        return file_paths
    
    def extract_function_targets_from_prompt(self, prompt_content: str) -> List[FunctionTarget]:
        """
        從 prompt 內容中提取函式目標（檔案+函式名稱），格式為每行: {檔案}|{函式}
        
        注意：
        - AS 模式會在呼叫此函式前，已經將 prompt 構造為單一函式（artificial_suicide_mode.py line 756）
        - 非 AS 模式使用 Coding Instruction 模板時，也會只處理第一個函式
        - 因此此函式統一只提取每行的第一個函式
        
        Args:
            prompt_content: prompt 內容（多行）
        Returns:
            List[FunctionTarget]: 函式目標列表
        """
        targets = []
        for line in prompt_content.strip().splitlines():
            parts = line.strip().split('|')
            if len(parts) == 2:
                file_path = parts[0].strip()
                func_name = parts[1].strip()
                if file_path and func_name:
                    # 支援多個函式名稱（以逗號、頓號、空格分隔）
                    func_names = re.split(r'[、,，\s]+', func_name)
                    func_names = [fn for fn in func_names if fn]
                    
                    # 統一只取第一個函式
                    # - AS 模式：artificial_suicide_mode.py 已經只傳入單一函式 (line 756)
                    # - 非 AS 模式：與 Coding Instruction 模板處理邏輯一致
                    if func_names:
                        func_names = [func_names[0]]
                    
                    target = FunctionTarget(
                        file_path=file_path,
                        function_names=func_names
                    )
                    targets.append(target)
                    self.logger.debug(f"  {file_path}: {', '.join(func_names)}")
        
        self.logger.info(f"從 prompt 中提取到 {len(targets)} 個檔案，共 {sum(len(t.function_names) for t in targets)} 個函式")
        return targets
    
    def scan_files(
        self, 
        project_path: Path, 
        file_paths: List[str], 
        cwe_type: str
    ) -> List[ScanResult]:
        """
        掃描指定的檔案列表
        
        Args:
            project_path: 專案根目錄
            file_paths: 要掃描的檔案路徑列表（相對於專案根目錄）
            cwe_type: CWE 類型（例如：'022'）
            
        Returns:
            List[ScanResult]: 掃描結果列表
        """
        self.logger.info(f"開始掃描 {len(file_paths)} 個檔案 (CWE-{cwe_type})...")
        
        results = []
        
        for file_path in file_paths:
            # 組合完整路徑
            full_path = project_path / file_path
            
            if not full_path.exists():
                self.logger.warning(f"檔案不存在，跳過: {full_path}")
                # 記錄為找不到的檔案
                results.append(ScanResult(
                    file_path=file_path,
                    has_vulnerability=False,
                    vulnerability_count=0,
                    details=[]
                ))
                continue
            
            # 使用 CWEDetector 掃描單一檔案，傳入專案名稱
            vulnerabilities = self.detector.scan_single_file(full_path, cwe_type, project_path.name)
            
            has_vuln = len(vulnerabilities) > 0
            
            result = ScanResult(
                file_path=file_path,
                has_vulnerability=has_vuln,
                vulnerability_count=len(vulnerabilities),
                details=vulnerabilities
            )
            
            results.append(result)
            
            status = "發現漏洞" if has_vuln else "安全"
            self.logger.info(f"  {file_path}: {status} ({len(vulnerabilities)} 個問題)")
        
        return results
    

    
    def _save_function_level_csv(
        self,
        file_path: Path,
        function_targets: List[FunctionTarget],
        scan_results: Dict[str, ScanResult],
        round_number: int = 0,
        line_number: int = 0,
        scanner_filter: str = None,
        append_mode: bool = False
    ):
        """
        儲存函式級別的掃描結果到 CSV
        
        每個函式一列，即使沒有漏洞也記錄
        格式: 輪數,行號,檔案路徑,修改前函式名稱,修改後函式名稱,漏洞數量,漏洞行號,掃描器,信心度,嚴重性,問題描述,掃描狀態,失敗原因
        
        Args:
            file_path: CSV 檔案路徑
            function_targets: 函式目標列表（從 prompt 提取）
            scan_results: 掃描結果字典（key=file_path）
            round_number: 輪數
            line_number: 行號
            scanner_filter: 掃描器過濾（'bandit' 或 'semgrep'），None 表示全部
            append_mode: 是否使用追加模式（True: 追加，False: 覆寫）
        """
        # 判斷是否需要寫入標題列（檔案不存在或非追加模式時寫入）
        write_header = not append_mode or not file_path.exists()
        
        # 根據模式選擇開啟方式
        mode = 'a' if append_mode else 'w'
        
        with open(file_path, mode, encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            
            # 寫入標題（僅在需要時）
            if write_header:
                # AS 模式：使用「修改前/後函式名稱」兩欄
                # 非 AS 模式：使用單一「函式名稱」欄
                if self.function_name_tracker:
                    writer.writerow([
                        '輪數',
                        '行號',
                        '檔案路徑',
                        '修改前函式名稱',
                        '修改後函式名稱',
                        '漏洞數量',
                        '漏洞行號',
                        '掃描器',
                        '信心度',
                        '嚴重性',
                        '問題描述',
                        '掃描狀態',
                        '失敗原因'
                    ])
                else:
                    writer.writerow([
                        '輪數',
                        '行號',
                        '檔案路徑',
                        '函式名稱',
                        '漏洞數量',
                        '漏洞行號',
                        '掃描器',
                        '信心度',
                        '嚴重性',
                        '問題描述',
                        '掃描狀態',
                        '失敗原因'
                    ])
            
            # 為每個目標函式寫一列
            for target in function_targets:
                for func_name in target.function_names:
                    # 查詢修改前和修改後的函式名稱（僅在 AS 模式下）
                    function_name = func_name  # 預設使用原始名稱（非 AS 模式）
                    before_name = func_name    # AS 模式使用
                    after_name = func_name     # AS 模式使用
                    
                    if self.function_name_tracker:
                        try:
                            # 獲取「修改前」名稱（= FunctionName_query 的「當前函式名稱」）
                            before_name, _ = self.function_name_tracker.get_function_name_for_round(
                                target.file_path, func_name, round_number
                            )
                            
                            # 獲取「修改後」名稱（= FunctionName_query 的「修改後函式名稱」）
                            # 從當前輪次的記錄中取得修改後的名稱
                            key = (target.file_path, func_name)
                            if key in self.function_name_tracker.function_mapping:
                                for round_num, modified_name, _ in self.function_name_tracker.function_mapping[key]:
                                    if round_num == round_number:
                                        after_name = modified_name
                                        break
                        except Exception as e:
                            self.logger.warning(f"⚠️  查詢函式名稱失敗: {e}，使用原始名稱")
                    
                    # 使用正確的 key 查找掃描結果（與 scan_from_prompt_function_level 中的 key 格式一致）
                    result_key = f"{target.file_path}::{func_name}"
                    file_result = scan_results.get(result_key)
                    
                    # 查找該函式的漏洞（可能有多個，來自不同掃描器）
                    func_vulns = []
                    scan_status = 'unknown'  # 預設為未知狀態（表示沒有掃描結果）
                    failure_reason = ''
                    has_scan_record = False  # 標記是否找到任何掃描記錄（包括成功但無漏洞的）
                    
                    if file_result and file_result.details:
                        for vuln in file_result.details:
                            # 首先檢查是否是掃描失敗記錄
                            if vuln.scan_status == 'failed':
                                # 如果有掃描器過濾，檢查是否符合
                                if scanner_filter is None or (vuln.scanner and vuln.scanner.value == scanner_filter):
                                    scan_status = 'failed'
                                    failure_reason = vuln.failure_reason or 'Unknown error'
                                    has_scan_record = True
                                    # 不繼續處理其他漏洞
                                    break
                            # 如果是成功記錄，檢查是否符合掃描器過濾
                            elif vuln.scan_status == 'success':
                                if scanner_filter is None or (vuln.scanner and vuln.scanner.value == scanner_filter):
                                    has_scan_record = True
                                    # 檢查是否是目標函式的漏洞記錄
                                    # 條件: function_name 匹配且有實際漏洞
                                    if vuln.function_name == func_name and (vuln.vulnerability_count is None or vuln.vulnerability_count > 0):
                                        # 找到該函式的漏洞記錄
                                        func_vulns.append(vuln)
                                    # 即使沒有漏洞，只要掃描成功就應該記錄（has_scan_record 已設置為 True）
                    
                    # 判斷最終狀態
                    if scan_status == 'failed':
                        # 已經標記為失敗
                        pass
                    elif has_scan_record:
                        # 找到了掃描記錄（可能有漏洞，也可能沒漏洞但掃描成功）
                        scan_status = 'success'
                    else:
                        # 沒有找到任何掃描記錄
                        scan_status = 'failed'
                        failure_reason = f'No scan results found for {scanner_filter or "any scanner"}'
                    
                    if scan_status == 'failed':
                        # 掃描失敗：記錄失敗資訊
                        if self.function_name_tracker:
                            writer.writerow([
                                round_number,
                                line_number,
                                target.file_path,
                                before_name,
                                after_name,
                                '',  # 漏洞數量
                                '',  # 漏洞行號
                                scanner_filter or '',
                                '',  # 信心度
                                '',  # 嚴重性
                                '',  # 問題描述
                                'failed',
                                failure_reason
                            ])
                        else:
                            writer.writerow([
                                round_number,
                                line_number,
                                target.file_path,
                                function_name,
                                '',  # 漏洞數量
                                '',  # 漏洞行號
                                scanner_filter or '',
                                '',  # 信心度
                                '',  # 嚴重性
                                '',  # 問題描述
                                'failed',
                                failure_reason
                            ])
                    elif func_vulns:
                        # 有漏洞：聚合同一函式的所有漏洞為一列
                        # 收集所有漏洞行號
                        all_vuln_lines = set()
                        for vuln in func_vulns:
                            if vuln.all_vulnerability_lines:
                                all_vuln_lines.update(vuln.all_vulnerability_lines)
                            else:
                                all_vuln_lines.add(vuln.line_start)
                        
                        # 格式化漏洞行號（排序後逗號分隔）
                        vuln_lines = ','.join(map(str, sorted(all_vuln_lines)))
                        
                        # 漏洞數量 = 總共有多少個漏洞記錄
                        total_vuln_count = len(func_vulns)
                        
                        # 收集所有掃描器、信心度、嚴重性、描述（可能有多個）
                        scanners = sorted(set(v.scanner.value for v in func_vulns if v.scanner))
                        confidences = sorted(set(v.confidence for v in func_vulns if v.confidence))
                        severities = sorted(set(v.severity for v in func_vulns if v.severity))
                        descriptions = [v.description for v in func_vulns if v.description]
                        
                        # 格式化為字串（多個值用分號分隔）
                        scanner_str = ';'.join(scanners) if scanners else ''
                        confidence_str = ';'.join(confidences) if confidences else ''
                        severity_str = ';'.join(severities) if severities else ''
                        description_str = ' | '.join(descriptions) if descriptions else ''
                        
                        if self.function_name_tracker:
                            writer.writerow([
                                round_number,
                                line_number,
                                target.file_path,
                                before_name,
                                after_name,
                                total_vuln_count,
                                vuln_lines,
                                scanner_str,
                                confidence_str,
                                severity_str,
                                description_str,
                                'success',
                                ''
                            ])
                        else:
                            writer.writerow([
                                round_number,
                                line_number,
                                target.file_path,
                                function_name,
                                total_vuln_count,
                                vuln_lines,
                                scanner_str,
                                confidence_str,
                                severity_str,
                                description_str,
                                'success',
                                ''
                            ])
                    else:
                        # 沒有漏洞但掃描成功：記錄安全狀態
                        if self.function_name_tracker:
                            writer.writerow([
                                round_number,
                                line_number,
                                target.file_path,
                                before_name,
                                after_name,
                                0,
                                '',
                                scanner_filter or '',
                                '',
                                '',
                                '',
                                'success',
                                ''
                            ])
                        else:
                            writer.writerow([
                                round_number,
                                line_number,
                                target.file_path,
                                function_name,
                                0,
                                '',
                                scanner_filter or '',
                                '',
                                '',
                                '',
                                'success',
                                ''
                            ])
        
        self.logger.debug(f"函式級別掃描結果已寫入: {file_path}")
    
    def scan_from_prompt_function_level(
        self,
        project_path: Path,
        project_name: str,
        prompt_content: str,
        cwe_type: str,
        round_number: int = 0,
        line_number: int = 0
    ) -> Tuple[bool, Optional[Path]]:
        """
        從 prompt 內容執行函式級別的掃描流程
        
        Args:
            project_path: 專案路徑
            project_name: 專案名稱
            prompt_content: prompt 內容
            cwe_type: CWE 類型
            round_number: 輪數（多輪互動時使用）
            line_number: 行號（逐行掃描時使用）
            
        Returns:
            Tuple[bool, Optional[Path]]: (是否成功, 掃描結果檔案路徑)
        """
        try:
            self.logger.create_separator(f"CWE-{cwe_type} 函式級別掃描: {project_name}")
            
            # 步驟1: 從 prompt 提取函式目標
            function_targets = self.extract_function_targets_from_prompt(prompt_content)
            
            if not function_targets:
                self.logger.warning("未從 prompt 中提取到任何函式目標")
                return False, None
            
            # 統計函式數量
            total_functions = sum(len(t.function_names) for t in function_targets)
            self.logger.info(f"提取到 {len(function_targets)} 個檔案，共 {total_functions} 個函式")
            
            # 步驟2: 為每個函式目標進行掃描（不去重，因為不同函式需要獨立的報告）
            scan_results_dict = {}
            for target in function_targets:
                file_path = target.file_path
                full_path = project_path / file_path
                
                if not full_path.exists():
                    self.logger.warning(f"檔案不存在: {file_path}")
                    # 為這個 target 的所有函式創建失敗記錄
                    for func_name in target.function_names:
                        key = f"{file_path}::{func_name}"
                        scan_results_dict[key] = ScanResult(
                            file_path=file_path,
                            has_vulnerability=False,
                            vulnerability_count=0,
                            details=[]
                        )
                    continue
                
                # 為每個函式進行掃描（生成獨立的原始報告）
                for func_name in target.function_names:
                    # 掃描檔案，傳入專案名稱、輪數和函式名稱
                    vulnerabilities = self.detector.scan_single_file(
                        full_path, 
                        cwe_type,
                        project_name=project_name,
                        round_number=round_number,
                        function_name=func_name
                    )
                    
                    # 使用檔案路徑::函式名稱作為 key，避免重複
                    key = f"{file_path}::{func_name}"
                    scan_results_dict[key] = ScanResult(
                        file_path=file_path,
                        has_vulnerability=len(vulnerabilities) > 0,
                        vulnerability_count=len(vulnerabilities),
                        details=vulnerabilities
                    )
                    
                    status = "發現漏洞" if vulnerabilities else "安全"
                    self.logger.info(f"  {file_path}::{func_name}: {status} ({len(vulnerabilities)} 個問題)")
            
            # 步驟3: 儲存函式級別結果（分離 Bandit 和 Semgrep）
            # 新結構：CWE-{cwe}/Bandit/{project}/第N輪/
            cwe_dir = self.output_dir / f"CWE-{cwe_type}"
            cwe_dir.mkdir(parents=True, exist_ok=True)
            
            # 建立掃描器目錄
            bandit_base_dir = cwe_dir / "Bandit"
            semgrep_base_dir = cwe_dir / "Semgrep"
            bandit_base_dir.mkdir(parents=True, exist_ok=True)
            semgrep_base_dir.mkdir(parents=True, exist_ok=True)
            
            # 建立專案目錄
            bandit_project_dir = bandit_base_dir / project_name
            semgrep_project_dir = semgrep_base_dir / project_name
            bandit_project_dir.mkdir(parents=True, exist_ok=True)
            semgrep_project_dir.mkdir(parents=True, exist_ok=True)
            
            # 建立輪數目錄
            round_folder_name = f"第{round_number}輪"
            bandit_round_dir = bandit_project_dir / round_folder_name
            semgrep_round_dir = semgrep_project_dir / round_folder_name
            bandit_round_dir.mkdir(parents=True, exist_ok=True)
            semgrep_round_dir.mkdir(parents=True, exist_ok=True)
            
            # 檔案路徑
            bandit_file = bandit_round_dir / f"{project_name}_function_level_scan.csv"
            semgrep_file = semgrep_round_dir / f"{project_name}_function_level_scan.csv"
            
            # 判斷是否使用追加模式（line_number > 1 表示不是第一行）
            append_mode = line_number > 1
            
            # 儲存 Bandit 結果
            self._save_function_level_csv(
                file_path=bandit_file,
                function_targets=function_targets,
                scan_results=scan_results_dict,
                round_number=round_number,
                line_number=line_number,
                scanner_filter='bandit',
                append_mode=append_mode
            )
            
            # 儲存 Semgrep 結果
            self._save_function_level_csv(
                file_path=semgrep_file,
                function_targets=function_targets,
                scan_results=scan_results_dict,
                round_number=round_number,
                line_number=line_number,
                scanner_filter='semgrep',
                append_mode=append_mode
            )
            
            mode_msg = "追加" if append_mode else "覆寫"
            self.logger.info(f"✅ Bandit 結果 ({mode_msg}): {bandit_file}")
            self.logger.info(f"✅ Semgrep 結果 ({mode_msg}): {semgrep_file}")
            
            # 步驟5: 輸出摘要
            total_vulns = sum(r.vulnerability_count for r in scan_results_dict.values())
            safe_funcs = total_functions - total_vulns
            
            self.logger.create_separator(f"函式級別掃描完成: {project_name}")
            self.logger.info(f"掃描函式數: {total_functions}")
            self.logger.info(f"發現漏洞: {total_vulns} 個函式")
            self.logger.info(f"安全函式: {safe_funcs} 個")
            
            # 返回兩個檔案路徑（主要返回 Bandit，因為相容性）
            return True, (bandit_file, semgrep_file)
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self.logger.error(f"函式級別掃描過程發生錯誤: {e}\n{error_details}")
            return False, None


# 全域實例
cwe_scan_manager = CWEScanManager()
