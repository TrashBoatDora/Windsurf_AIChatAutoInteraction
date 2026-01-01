# -*- coding: utf-8 -*-
"""
Vicious Pattern Manager - 漏洞 Pattern 備份管理器

功能：
1. 在 Phase 2 掃描出漏洞後，記錄漏洞資訊（不備份）
2. 在 Phase 2 undo 完成後，備份該檔案的 Phase 1 pattern
3. 維護 vicious_pattern 目錄結構（與源專案結構一致）
4. 生成只包含有漏洞的 file|function 的 prompt.txt

使用流程：
1. Phase 2 掃描時調用 add_vulnerable_function() 記錄漏洞
2. Phase 2 undo 後調用 backup_round_patterns() 備份當輪檔案
3. 所有輪數完成後調用 finalize() 生成 prompt.txt
"""

import shutil
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field

from src.logger import get_logger
from config.config import config


@dataclass
class VulnerableFunction:
    """記錄有漏洞的函式資訊"""
    file_path: str          # 相對於專案的檔案路徑
    function_name: str      # 函式名稱
    round_number: int       # 發現漏洞的輪數
    vulnerability_count: int = 0  # 漏洞數量
    scanner: str = ""       # 掃描器（semgrep/bandit）
    backed_up: bool = False # 是否已備份


class ViciousPatternManager:
    """漏洞 Pattern 備份管理器"""
    
    def __init__(self, project_name: str, project_path: Path, cwe_type: str):
        """
        初始化管理器
        
        Args:
            project_name: 專案名稱
            project_path: 專案完整路徑
            cwe_type: CWE 類型（如 "022", "327"）
        """
        self.logger = get_logger("ViciousPatternManager")
        self.project_name = project_name
        self.project_path = Path(project_path)
        self.cwe_type = cwe_type
        
        # 輸出目錄
        self.vicious_pattern_base = config.VICIOUS_PATTERN_DIR
        self.project_output_dir = self.vicious_pattern_base / project_name
        
        # 記錄已備份的檔案和有漏洞的函式
        self.backed_up_files: Set[str] = set()  # 已備份的檔案路徑（相對路徑）
        self.vulnerable_functions: List[VulnerableFunction] = []
        
        # 注意：不在這裡建立目錄，只有在實際需要備份時才建立
        
        self.logger.info(f"✅ ViciousPatternManager 初始化完成")
        self.logger.info(f"   專案: {project_name}")
        self.logger.info(f"   輸出目錄: {self.project_output_dir}")
    
    def add_vulnerable_function(self, file_path: str, function_name: str, 
                                 round_number: int, vulnerability_count: int = 1,
                                 scanner: str = "") -> None:
        """
        記錄發現的漏洞函式（只記錄，不備份）
        
        此方法應在 Phase 2 掃描完成後、undo 之前呼叫
        
        Args:
            file_path: 相對於專案的檔案路徑
            function_name: 有漏洞的函式名稱
            round_number: 發現漏洞的輪數
            vulnerability_count: 漏洞數量
            scanner: 掃描器名稱
        """
        vuln_func = VulnerableFunction(
            file_path=file_path,
            function_name=function_name,
            round_number=round_number,
            vulnerability_count=vulnerability_count,
            scanner=scanner,
            backed_up=False
        )
        self.vulnerable_functions.append(vuln_func)
        self.logger.debug(f"  📝 記錄漏洞: {file_path}::{function_name} (輪數: {round_number})")
    
    def backup_round_patterns(self, round_number: int) -> int:
        """
        備份指定輪數的所有漏洞 pattern 檔案
        
        此方法應在 Phase 2 undo 完成後呼叫，此時檔案已恢復到 Phase 1 的狀態
        （變數名稱已修改但沒有漏洞程式碼）
        
        Args:
            round_number: 輪數
            
        Returns:
            int: 本輪實際備份的檔案數量
        """
        # 找出本輪尚未備份的漏洞函式
        round_vulns = [vf for vf in self.vulnerable_functions 
                       if vf.round_number == round_number and not vf.backed_up]
        
        if not round_vulns:
            self.logger.info(f"  ℹ️  第 {round_number} 輪無需備份的新漏洞")
            return 0
        
        # 收集需要備份的檔案（去重）
        files_to_backup: Set[str] = set()
        for vf in round_vulns:
            if vf.file_path not in self.backed_up_files:
                files_to_backup.add(vf.file_path)
        
        # 執行備份
        backup_count = 0
        for relative_file_path in files_to_backup:
            if self._backup_single_file(relative_file_path):
                backup_count += 1
        
        # 標記漏洞函式為已備份
        for vf in round_vulns:
            vf.backed_up = True
        
        self.logger.info(f"  📦 第 {round_number} 輪備份完成: {backup_count} 個新檔案, {len(round_vulns)} 個漏洞函式")
        
        return backup_count
    
    def _backup_single_file(self, relative_file_path: str) -> bool:
        """
        備份單一檔案
        
        Args:
            relative_file_path: 相對於專案的檔案路徑
            
        Returns:
            bool: 是否成功備份
        """
        try:
            # 如果檔案已備份，跳過
            if relative_file_path in self.backed_up_files:
                return False
            
            # 構建源檔案和目標檔案路徑
            source_file = self.project_path / relative_file_path
            target_file = self.project_output_dir / relative_file_path
            
            # 檢查源檔案是否存在
            if not source_file.exists():
                self.logger.error(f"  ❌ 源檔案不存在: {source_file}")
                return False
            
            # 確保專案輸出目錄和目標檔案父目錄存在（只在需要時建立）
            self.project_output_dir.mkdir(parents=True, exist_ok=True)
            target_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 複製檔案
            shutil.copy2(source_file, target_file)
            self.backed_up_files.add(relative_file_path)
            
            self.logger.info(f"    ✅ 已備份: {relative_file_path}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"  ❌ 備份檔案失敗 ({relative_file_path}): {e}")
            return False
    
    def generate_prompt_txt(self) -> bool:
        """
        生成只包含有漏洞函式的 prompt.txt
        
        格式: filepath|function1()、function2()
        （同一檔案的多個函式會合併在同一行）
        
        Returns:
            bool: 是否成功生成
        """
        try:
            if not self.vulnerable_functions:
                self.logger.warning("  ⚠️  沒有記錄到任何漏洞函式，不生成 prompt.txt")
                return False
            
            # 按檔案路徑分組函式
            file_functions: Dict[str, List[str]] = {}
            for vuln_func in self.vulnerable_functions:
                file_path = vuln_func.file_path
                func_name = vuln_func.function_name
                
                # 確保函式名稱包含括號
                if not func_name.endswith('()'):
                    func_name = func_name + '()'
                
                if file_path not in file_functions:
                    file_functions[file_path] = []
                
                # 避免重複添加同一函式
                if func_name not in file_functions[file_path]:
                    file_functions[file_path].append(func_name)
            
            # 生成 prompt.txt 內容
            prompt_lines = []
            for file_path in sorted(file_functions.keys()):
                functions = file_functions[file_path]
                # 使用中文頓號連接多個函式
                functions_str = '、'.join(sorted(functions))
                prompt_lines.append(f"{file_path}|{functions_str}")
            
            # 寫入檔案（確保目錄存在）
            self.project_output_dir.mkdir(parents=True, exist_ok=True)
            prompt_file = self.project_output_dir / "prompt.txt"
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(prompt_lines))
            
            self.logger.info(f"  ✅ 已生成 prompt.txt: {prompt_file}")
            self.logger.info(f"     包含 {len(file_functions)} 個檔案, {len(self.vulnerable_functions)} 個漏洞函式")
            
            return True
            
        except Exception as e:
            self.logger.error(f"  ❌ 生成 prompt.txt 失敗: {e}")
            return False
    
    def finalize(self) -> Tuple[int, int]:
        """
        完成備份並生成 prompt.txt
        
        如果沒有漏洞，會刪除空的專案目錄
        
        Returns:
            Tuple[int, int]: (備份的檔案數, 記錄的漏洞函式數)
        """
        self.logger.create_separator(f"📦 完成 Vicious Pattern 備份")
        
        # 檢查是否有漏洞
        if not self.has_vulnerability():
            self.logger.info(f"  ℹ️  專案 {self.project_name} 沒有發現漏洞，跳過備份")
            # 如果目錄存在但是空的，刪除它
            self._cleanup_empty_directory()
            return 0, 0
        
        # 生成 prompt.txt
        self.generate_prompt_txt()
        
        # 輸出統計
        file_count = len(self.backed_up_files)
        func_count = len(self.vulnerable_functions)
        
        self.logger.info(f"📊 備份統計:")
        self.logger.info(f"   專案: {self.project_name}")
        self.logger.info(f"   備份檔案數: {file_count}")
        self.logger.info(f"   漏洞函式數: {func_count}")
        self.logger.info(f"   輸出目錄: {self.project_output_dir}")
        
        return file_count, func_count
    
    def _cleanup_empty_directory(self) -> None:
        """
        清理空的專案目錄
        
        如果專案目錄存在但為空（沒有檔案），則刪除它
        """
        try:
            if self.project_output_dir.exists():
                # 檢查目錄是否為空
                contents = list(self.project_output_dir.iterdir())
                if not contents:
                    self.project_output_dir.rmdir()
                    self.logger.info(f"  🗑️  已刪除空的專案目錄: {self.project_output_dir}")
                else:
                    self.logger.debug(f"  ℹ️  專案目錄非空，保留: {self.project_output_dir}")
        except Exception as e:
            self.logger.warning(f"  ⚠️  清理空目錄時發生錯誤: {e}")
    
    def has_vulnerability(self) -> bool:
        """檢查是否有記錄到任何漏洞"""
        return len(self.vulnerable_functions) > 0
    
    def get_summary(self) -> Dict:
        """
        獲取備份摘要
        
        Returns:
            Dict: 包含備份統計的字典
        """
        return {
            "project_name": self.project_name,
            "cwe_type": self.cwe_type,
            "backed_up_files": list(self.backed_up_files),
            "vulnerable_functions": [
                {
                    "file_path": vf.file_path,
                    "function_name": vf.function_name,
                    "round_number": vf.round_number,
                    "vulnerability_count": vf.vulnerability_count,
                    "scanner": vf.scanner
                }
                for vf in self.vulnerable_functions
            ],
            "output_dir": str(self.project_output_dir)
        }


def create_vicious_pattern_manager(project_name: str, project_path: Path, 
                                    cwe_type: str) -> ViciousPatternManager:
    """
    便捷函式：建立 ViciousPatternManager 實例
    
    Args:
        project_name: 專案名稱
        project_path: 專案完整路徑
        cwe_type: CWE 類型
        
    Returns:
        ViciousPatternManager: 管理器實例
    """
    return ViciousPatternManager(project_name, project_path, cwe_type)
