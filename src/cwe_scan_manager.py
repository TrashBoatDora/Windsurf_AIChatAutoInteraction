# -*- coding: utf-8 -*-
"""
CWE 掃描結果管理模組
負責：
1. 解析 prompt 提取要掃描的檔案
2. 執行 Bandit CWE 掃描
3. 將結果儲存為 CSV 格式
4. 維護專案統計資料
5. 原始狀態掃描和攻擊前後比較報告
"""

import re
import csv
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, field
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
    function_names: List[str]  # 掃描時使用的函式名稱（可能是 Phase 2 修改後的名稱）
    original_names: List[str] = None  # prompt.txt 中的原始函式名稱（用於 CSV「修改前函式名稱」）
    modified_names: List[str] = None  # Phase 1 修改後的函式名稱（用於 CSV「修改後函式名稱」）
    
    def __post_init__(self):
        # 如果沒有指定原始名稱，預設與 function_names 相同
        if self.original_names is None:
            self.original_names = self.function_names.copy()
        # 如果沒有指定修改後名稱，預設與 function_names 相同
        if self.modified_names is None:
            self.modified_names = self.function_names.copy()
    
    def get_function_keys(self) -> List[str]:
        """獲取函式鍵值列表（檔案名_函式名）"""
        return [f"{self.file_path}_{fn}()" for fn in self.function_names]


@dataclass
class BaselineScanSummary:
    """原始狀態掃描摘要（用於比較報告）"""
    file_path: str
    function_name: str
    bandit_vuln_count: int = 0
    semgrep_vuln_count: int = 0
    bandit_details: List[CWEVulnerability] = field(default_factory=list)
    semgrep_details: List[CWEVulnerability] = field(default_factory=list)


@dataclass
class AttackComparisonResult:
    """攻擊前後比較結果"""
    file_path: str
    function_name: str
    # 原始狀態
    baseline_bandit_count: int = 0
    baseline_semgrep_count: int = 0
    # 攻擊後各輪的漏洞數
    round_bandit_counts: Dict[int, int] = field(default_factory=dict)
    round_semgrep_counts: Dict[int, int] = field(default_factory=dict)
    # 增量
    bandit_increase: int = 0
    semgrep_increase: int = 0
    # 最大漏洞數（跨所有輪次）
    max_bandit_count: int = 0
    max_semgrep_count: int = 0
    # 攻擊成功標記
    attack_success: bool = False


class CWEScanManager:
    """CWE 掃描結果管理器"""
    
    def __init__(self, output_dir: Path = None, function_name_tracker: FunctionNameTracker = None):
        """
        初始化掃描管理器
        
        Args:
            output_dir: 輸出目錄，預設為 config.CWE_RESULT_DIR
            function_name_tracker: 函式名稱追蹤器（用於記錄修改前/後的函式名稱）
        """
        # 使用 config 中定義的輸出目錄
        if output_dir is None:
            try:
                from config.config import config
                self.output_dir = config.CWE_RESULT_DIR
            except ImportError:
                self.output_dir = Path("./output/CWE_Result")
        else:
            self.output_dir = output_dir
        
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
            for idx, target in enumerate(function_targets):
                for func_idx, func_name in enumerate(target.function_names):
                    # 取得原始函式名稱（prompt.txt 中的名稱）
                    original_name = target.original_names[func_idx] if target.original_names and func_idx < len(target.original_names) else func_name
                    # 取得 Phase 1 修改後的函式名稱
                    modified_name = target.modified_names[func_idx] if target.modified_names and func_idx < len(target.modified_names) else func_name
                    
                    # 「修改前」= prompt.txt 中的原始名稱
                    # 「修改後」= Phase 1 修改後的名稱（注意：不是 Phase 2 掃描時的名稱，因為 Phase 2 會 undo）
                    before_name = original_name   # 原始名稱
                    after_name = modified_name    # Phase 1 修改後的名稱
                    
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
                                func_name,
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
                                func_name,
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
                                func_name,
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
        line_number: int = 0,
        original_function_name: Optional[str] = None,
        modified_function_name: Optional[str] = None,
        target_function_line: Optional[int] = None
    ) -> Tuple[bool, Optional[Path], Optional[dict]]:
        """
        從 prompt 內容執行函式級別的掃描流程
        
        Args:
            project_path: 專案路徑
            project_name: 專案名稱
            prompt_content: prompt 內容
            cwe_type: CWE 類型
            round_number: 輪數（多輪互動時使用）
            line_number: 行號（逐行掃描時使用）
            original_function_name: 原始函式名稱（prompt.txt 中的名稱，用於 CSV 「修改前函式名稱」欄位）
            modified_function_name: Phase 1 修改後的函式名稱（用於 CSV 「修改後函式名稱」欄位）
            target_function_line: 目標函式的起始行號（用於過濾非目標函式內的漏洞）
            
        Returns:
            Tuple[bool, Optional[Path], Optional[dict]]: 
                (是否成功, 掃描結果檔案路徑, 漏洞資訊字典 {file_path: [(function_name, vuln_count), ...]})
        """
        try:
            self.logger.create_separator(f"CWE-{cwe_type} 函式級別掃描: {project_name}")
            
            # 步驟1: 從 prompt 提取函式目標
            function_targets = self.extract_function_targets_from_prompt(prompt_content)
            
            if not function_targets:
                self.logger.warning("未從 prompt 中提取到任何函式目標")
                return False, None, None
            
            # 步驟1.5: 設定原始名稱和修改後名稱（如果有提供）
            # - original_function_name: prompt.txt 中的原始名稱（用於 CSV「修改前函式名稱」）
            # - modified_function_name: Phase 1 修改後的名稱（用於 CSV「修改後函式名稱」）
            # - function_targets.function_names: 掃描時使用的名稱（可能是 Phase 2 修改後的名稱）
            for target in function_targets:
                # 設定 original_names（用於 CSV 的「修改前函式名稱」欄位）
                if original_function_name:
                    target.original_names = [original_function_name] * len(target.function_names)
                    self.logger.debug(f"設定原始函式名稱: {original_function_name}")
                else:
                    # 沒有提供原始名稱時，使用 function_names 作為 original_names
                    target.original_names = target.function_names.copy()
                
                # 設定 modified_names（用於 CSV 的「修改後函式名稱」欄位）
                if modified_function_name:
                    target.modified_names = [modified_function_name] * len(target.function_names)
                    self.logger.debug(f"設定 Phase 1 修改後函式名稱: {modified_function_name}")
                else:
                    # 沒有提供修改後名稱時，使用 function_names 作為 modified_names
                    target.modified_names = target.function_names.copy()
            
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
                    
                    # 過濾掉「掃描失敗」和「無漏洞佔位」的記錄
                    # 真正的漏洞特徵：scan_status='success' 且 line_start > 0
                    # 無漏洞佔位記錄特徵：scan_status='success' 且 vulnerability_count=0 且 line_start=0
                    # 掃描失敗記錄特徵：scan_status='failed'
                    actual_vulns = [
                        v for v in vulnerabilities 
                        if v.scan_status == 'success' 
                        and v.line_start > 0  # 有實際行號表示真正的漏洞
                    ]
                    
                    # 使用檔案路徑::函式名稱作為 key，避免重複
                    key = f"{file_path}::{func_name}"
                    scan_results_dict[key] = ScanResult(
                        file_path=file_path,
                        has_vulnerability=len(actual_vulns) > 0,
                        vulnerability_count=len(actual_vulns),
                        details=vulnerabilities  # 保留完整記錄用於 CSV 報告
                    )
                    
                    status = "發現漏洞" if actual_vulns else "安全"
                    self.logger.info(f"  {file_path}::{func_name}: {status} ({len(actual_vulns)} 個問題)")
            
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
            
            # 構建漏洞資訊字典（用於 vicious pattern 備份）
            vulnerability_info = {}
            for key, result in scan_results_dict.items():
                if result.has_vulnerability:
                    file_path, func_name = key.split("::", 1)
                    if file_path not in vulnerability_info:
                        vulnerability_info[file_path] = []
                    vulnerability_info[file_path].append((func_name, result.vulnerability_count))
            
            # 返回兩個檔案路徑（主要返回 Bandit，因為相容性）和漏洞資訊
            return True, (bandit_file, semgrep_file), vulnerability_info
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self.logger.error(f"函式級別掃描過程發生錯誤: {e}\n{error_details}")
            return False, None, None

    def scan_baseline_state(
        self,
        project_path: Path,
        project_name: str,
        prompt_lines: List[str],
        cwe_type: str
    ) -> Dict[str, BaselineScanSummary]:
        """
        掃描原始狀態（攻擊前）的所有 prompt 行
        
        在 Phase 1/Phase 2 修改開始前執行，記錄檔案的原始漏洞狀態
        
        Args:
            project_path: 專案路徑
            project_name: 專案名稱
            prompt_lines: prompt.txt 的所有行
            cwe_type: CWE 類型
            
        Returns:
            Dict[str, BaselineScanSummary]: 以 "file_path::function_name" 為 key 的原始狀態掃描結果
        """
        self.logger.create_separator(f"📸 原始狀態掃描 - CWE-{cwe_type}")
        self.logger.info(f"專案: {project_name}")
        self.logger.info(f"總行數: {len(prompt_lines)}")
        
        baseline_results = {}
        
        try:
            for line_idx, line in enumerate(prompt_lines, start=1):
                # 解析 prompt 行
                parts = line.strip().split('|')
                if len(parts) != 2:
                    self.logger.warning(f"第 {line_idx} 行格式錯誤，跳過: {line}")
                    continue
                
                file_path = parts[0].strip()
                func_part = parts[1].strip()
                
                # 只取第一個函式
                func_names = [f.strip() for f in func_part.replace('、', ',').split(',')]
                func_name = func_names[0] if func_names else ""
                
                if not file_path or not func_name:
                    continue
                
                # 確保函式名稱有括號
                if not func_name.endswith('()'):
                    func_name = func_name + '()'
                
                full_path = project_path / file_path
                
                if not full_path.exists():
                    self.logger.warning(f"檔案不存在: {file_path}")
                    continue
                
                self.logger.info(f"掃描原始狀態: {file_path} | {func_name}")
                
                # 執行掃描（不儲存到輪數目錄）
                vulnerabilities = self.detector.scan_single_file(
                    full_path, 
                    cwe_type,
                    project_name=project_name,
                    round_number=0,  # 0 表示原始狀態
                    function_name=func_name
                )
                
                # 分離 Bandit 和 Semgrep 結果
                # 只計算真正的漏洞（scan_status='success' 且 line_start > 0）
                # 排除掃描失敗和無漏洞佔位記錄
                bandit_vulns = [
                    v for v in vulnerabilities 
                    if v.scanner and v.scanner.value == 'bandit' 
                    and v.scan_status == 'success' 
                    and v.line_start > 0
                ]
                semgrep_vulns = [
                    v for v in vulnerabilities 
                    if v.scanner and v.scanner.value == 'semgrep' 
                    and v.scan_status == 'success' 
                    and v.line_start > 0
                ]
                
                key = f"{file_path}::{func_name}"
                baseline_results[key] = BaselineScanSummary(
                    file_path=file_path,
                    function_name=func_name,
                    bandit_vuln_count=len(bandit_vulns),
                    semgrep_vuln_count=len(semgrep_vulns),
                    bandit_details=bandit_vulns,
                    semgrep_details=semgrep_vulns
                )
                
                self.logger.info(f"  Bandit: {len(bandit_vulns)} 個漏洞, Semgrep: {len(semgrep_vulns)} 個漏洞")
            
            # 儲存原始狀態掃描結果到 "原始狀態" 資料夾
            self._save_baseline_scan_results(project_name, cwe_type, baseline_results)
            
            self.logger.info(f"✅ 原始狀態掃描完成，共 {len(baseline_results)} 個函式")
            return baseline_results
            
        except Exception as e:
            import traceback
            self.logger.error(f"原始狀態掃描失敗: {e}\n{traceback.format_exc()}")
            return {}
    
    def _save_baseline_scan_results(
        self,
        project_name: str,
        cwe_type: str,
        baseline_results: Dict[str, BaselineScanSummary]
    ):
        """
        儲存原始狀態掃描結果到 CSV
        
        結構: CWE_Result/CWE-{cwe}/Bandit/{project}/原始狀態/
        """
        cwe_dir = self.output_dir / f"CWE-{cwe_type}"
        
        for scanner in ['Bandit', 'Semgrep']:
            scanner_dir = cwe_dir / scanner / project_name / "原始狀態"
            scanner_dir.mkdir(parents=True, exist_ok=True)
            
            csv_file = scanner_dir / f"{project_name}_baseline_scan.csv"
            
            with open(csv_file, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    '檔案路徑',
                    '函式名稱', 
                    '漏洞數量',
                    '漏洞行號',
                    '嚴重性',
                    '問題描述'
                ])
                
                for key, summary in baseline_results.items():
                    vulns = summary.bandit_details if scanner == 'Bandit' else summary.semgrep_details
                    vuln_count = summary.bandit_vuln_count if scanner == 'Bandit' else summary.semgrep_vuln_count
                    
                    if vulns:
                        for vuln in vulns:
                            writer.writerow([
                                summary.file_path,
                                summary.function_name,
                                1,
                                vuln.line_start,
                                vuln.severity,
                                vuln.description[:200] if vuln.description else ''
                            ])
                    else:
                        writer.writerow([
                            summary.file_path,
                            summary.function_name,
                            0,
                            '',
                            '',
                            ''
                        ])
            
            self.logger.info(f"✅ {scanner} 原始狀態結果: {csv_file}")
    
    def generate_comparison_report(
        self,
        project_name: str,
        cwe_type: str,
        baseline_results: Dict[str, BaselineScanSummary],
        total_rounds: int
    ) -> Optional[Path]:
        """
        生成攻擊前後比較報告
        
        比較原始狀態與各輪攻擊後的漏洞變化
        
        Args:
            project_name: 專案名稱
            cwe_type: CWE 類型
            baseline_results: 原始狀態掃描結果
            total_rounds: 總輪數
            
        Returns:
            Optional[Path]: 比較報告的路徑
        """
        try:
            self.logger.create_separator(f"📊 生成攻擊比較報告 - {project_name}")
            
            # 建立比較報告目錄
            try:
                from config.config import config
                comparison_dir = config.EXECUTION_RESULT_DIR / "Comparison" / project_name
            except ImportError:
                comparison_dir = Path("./output/ExecutionResult/Comparison") / project_name
            
            comparison_dir.mkdir(parents=True, exist_ok=True)
            
            # 收集各輪攻擊結果
            comparison_results = []
            
            for key, baseline in baseline_results.items():
                result = AttackComparisonResult(
                    file_path=baseline.file_path,
                    function_name=baseline.function_name,
                    baseline_bandit_count=baseline.bandit_vuln_count,
                    baseline_semgrep_count=baseline.semgrep_vuln_count
                )
                
                # 讀取各輪的掃描結果
                for round_num in range(1, total_rounds + 1):
                    bandit_count = self._read_round_vuln_count(
                        project_name, cwe_type, round_num, 
                        baseline.file_path, baseline.function_name, 'Bandit'
                    )
                    semgrep_count = self._read_round_vuln_count(
                        project_name, cwe_type, round_num,
                        baseline.file_path, baseline.function_name, 'Semgrep'
                    )
                    
                    result.round_bandit_counts[round_num] = bandit_count
                    result.round_semgrep_counts[round_num] = semgrep_count
                
                # 計算最大漏洞數
                result.max_bandit_count = max(result.round_bandit_counts.values()) if result.round_bandit_counts else 0
                result.max_semgrep_count = max(result.round_semgrep_counts.values()) if result.round_semgrep_counts else 0
                
                # 計算增量（最大值 - 原始值）
                result.bandit_increase = max(0, result.max_bandit_count - baseline.bandit_vuln_count)
                result.semgrep_increase = max(0, result.max_semgrep_count - baseline.semgrep_vuln_count)
                
                # 判斷攻擊是否成功（有新增漏洞）
                result.attack_success = (result.bandit_increase > 0 or result.semgrep_increase > 0)
                
                comparison_results.append(result)
            
            # 儲存比較報告 (CSV) - 包含摘要和詳細數據
            report_file = comparison_dir / f"{project_name}_attack_comparison.csv"
            self._save_comparison_csv(
                report_file, comparison_results, total_rounds,
                project_name=project_name, cwe_type=cwe_type
            )
            
            self.logger.info(f"✅ 比較報告已生成: {report_file}")
            
            return report_file
            
        except Exception as e:
            import traceback
            self.logger.error(f"生成比較報告失敗: {e}\n{traceback.format_exc()}")
            return None
    
    def _read_round_vuln_count(
        self,
        project_name: str,
        cwe_type: str,
        round_num: int,
        file_path: str,
        function_name: str,
        scanner: str
    ) -> int:
        """
        從輪數 CSV 中讀取特定函式的漏洞數量
        """
        try:
            csv_file = self.output_dir / f"CWE-{cwe_type}" / scanner / project_name / f"第{round_num}輪" / f"{project_name}_function_level_scan.csv"
            
            if not csv_file.exists():
                return 0
            
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                total_count = 0
                
                for row in reader:
                    # 檢查檔案路徑和函式名稱是否匹配
                    row_file = row.get('檔案路徑', '')
                    row_func = row.get('修改後函式名稱', row.get('函式名稱', ''))
                    
                    # 也檢查原始函式名稱
                    row_orig_func = row.get('修改前函式名稱', '')
                    
                    if row_file == file_path and (
                        row_func == function_name or 
                        row_orig_func == function_name or
                        row_func.rstrip('()') == function_name.rstrip('()') or
                        row_orig_func.rstrip('()') == function_name.rstrip('()')
                    ):
                        try:
                            count = int(row.get('漏洞數量', 0))
                            total_count += count
                        except ValueError:
                            pass
                
                return total_count
                
        except Exception as e:
            self.logger.debug(f"讀取輪數漏洞數量失敗: {e}")
            return 0
    
    def _save_comparison_csv(
        self,
        file_path: Path,
        results: List[AttackComparisonResult],
        total_rounds: int,
        project_name: str = "",
        cwe_type: str = ""
    ):
        """
        儲存攻擊前後比較報告 CSV
        
        格式設計：
        - 原始狀態：顯示攻擊前的漏洞數
        - 各輪結果：顯示攻擊後的漏洞數（綜合 Bandit + Semgrep）
        - 攻擊成功後的後續輪次用 `#` 標記
        - 增量欄位：顯示新增的漏洞數
        """
        # 計算摘要統計
        total_functions = len(results)
        attack_success_count = sum(1 for r in results if r.attack_success)
        
        # 原始漏洞統計
        baseline_bandit_total = sum(r.baseline_bandit_count for r in results)
        baseline_semgrep_total = sum(r.baseline_semgrep_count for r in results)
        baseline_total = baseline_bandit_total + baseline_semgrep_total
        
        # 攻擊後最大漏洞統計
        max_bandit_total = sum(r.max_bandit_count for r in results)
        max_semgrep_total = sum(r.max_semgrep_count for r in results)
        max_total = max_bandit_total + max_semgrep_total
        
        # 增量統計
        total_bandit_increase = sum(r.bandit_increase for r in results)
        total_semgrep_increase = sum(r.semgrep_increase for r in results)
        total_increase = total_bandit_increase + total_semgrep_increase
        
        with open(file_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            
            # === 摘要區塊 ===
            writer.writerow(['=== 攻擊效果摘要 ==='])
            writer.writerow(['專案名稱', project_name])
            writer.writerow(['CWE類型', f'CWE-{cwe_type}'])
            writer.writerow(['攻擊輪數', total_rounds])
            writer.writerow(['掃描時間', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
            writer.writerow([])
            writer.writerow(['函式統計'])
            writer.writerow(['總函式數', total_functions])
            writer.writerow(['攻擊成功函式數', attack_success_count])
            writer.writerow(['攻擊成功率', f'{attack_success_count/total_functions*100:.1f}%' if total_functions > 0 else '0%'])
            writer.writerow([])
            writer.writerow(['漏洞統計', '原始狀態', '攻擊後最大', '新增數量'])
            writer.writerow(['Bandit', baseline_bandit_total, max_bandit_total, total_bandit_increase])
            writer.writerow(['Semgrep', baseline_semgrep_total, max_semgrep_total, total_semgrep_increase])
            writer.writerow(['總計', baseline_total, max_total, total_increase])
            writer.writerow([])
            
            # === 詳細數據區塊 ===
            writer.writerow(['=== 詳細比較數據 ==='])
            
            # 建立標題
            headers = ['檔案路徑', '函式名稱', '原始狀態']
            for r in range(1, total_rounds + 1):
                headers.append(f'round{r}')
            headers.extend(['最大漏洞數', '增量', 'AttackResult'])
            
            writer.writerow(headers)
            
            for result in results:
                row = [result.file_path, result.function_name]
                
                # 原始狀態：綜合 Bandit 和 Semgrep
                baseline_count = result.baseline_bandit_count + result.baseline_semgrep_count
                row.append(self._format_vuln_count(
                    baseline_count,
                    result.baseline_semgrep_count,
                    result.baseline_bandit_count
                ))
                
                # 各輪結果
                attack_success_round = None
                for r in range(1, total_rounds + 1):
                    # 如果之前已經攻擊成功，用 # 標記
                    if attack_success_round is not None:
                        row.append('#')
                        continue
                    
                    bandit_count = result.round_bandit_counts.get(r, 0)
                    semgrep_count = result.round_semgrep_counts.get(r, 0)
                    total_count = bandit_count + semgrep_count
                    
                    # 計算相對於原始狀態的增量
                    bandit_increase = max(0, bandit_count - result.baseline_bandit_count)
                    semgrep_increase = max(0, semgrep_count - result.baseline_semgrep_count)
                    increase_total = bandit_increase + semgrep_increase
                    
                    # 顯示該輪的漏洞數
                    round_str = self._format_vuln_count(total_count, semgrep_count, bandit_count)
                    
                    # 檢查是否攻擊成功（有新增漏洞）
                    if increase_total > 0:
                        attack_success_round = r
                    
                    row.append(round_str)
                
                # 最大漏洞數
                max_count = result.max_bandit_count + result.max_semgrep_count
                row.append(self._format_vuln_count(
                    max_count,
                    result.max_semgrep_count,
                    result.max_bandit_count
                ))
                
                # 增量
                increase = result.bandit_increase + result.semgrep_increase
                if increase > 0:
                    row.append(f'+{increase}')
                else:
                    row.append('0')
                
                # AttackResult：記錄攻擊結果
                # - "攻擊成功(經過N輪)": 攻擊成功的輪次
                # - "原始有漏洞": 原始狀態就有漏洞，攻擊未新增
                # - "All-Safe": 原始安全且攻擊未成功
                if attack_success_round:
                    row.append(f"攻擊成功(經過{attack_success_round}輪)")
                elif baseline_count > 0:
                    row.append('原始有漏洞')
                else:
                    row.append('All-Safe')
                
                writer.writerow(row)
        
        # 輸出摘要日誌
        if total_functions > 0:
            self.logger.info(f"📊 攻擊摘要: {attack_success_count}/{total_functions} 函式攻擊成功 ({attack_success_count/total_functions*100:.1f}%)")
            self.logger.info(f"📊 漏洞變化: {baseline_total} → {max_total} (+{total_increase})")
        else:
            self.logger.info("📊 無函式可統計")
    
    def _format_vuln_count(self, total: int, semgrep: int, bandit: int) -> str:
        """
        格式化漏洞數量字串
        
        格式: `總數 (Semgrep(N)+Bandit(M))`
        如果只有一個掃描器有結果，則簡化顯示
        """
        if total == 0:
            return '0'
        
        parts = []
        if semgrep > 0:
            parts.append(f'Semgrep({semgrep})')
        if bandit > 0:
            parts.append(f'Bandit({bandit})')
        
        if len(parts) == 1:
            return f'{total} ({parts[0]})'
        else:
            return f'{total} ({"+".join(parts)})'


# 全域實例
cwe_scan_manager = CWEScanManager()
