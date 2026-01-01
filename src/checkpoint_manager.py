# -*- coding: utf-8 -*-
"""
Checkpoint Manager for execution state persistence and recovery.

This module provides functionality to save and restore execution state,
enabling resume from interruption points in both AS Mode and Non-AS Mode.

Key features:
- Automatic checkpoint saving during execution
- Detection of incomplete executions
- Resume from exact interruption point
- Support for both AS Mode and Non-AS Mode workflows
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from src.logger import get_logger
except ImportError:
    from logger import get_logger

logger = get_logger("CheckpointManager")


class CheckpointManager:
    """
    Manages execution checkpoints for resumable CWE scanning workflows.
    
    Checkpoint structure:
    {
        "version": "1.0",
        "created_at": "2025-12-28T19:08:11",
        "updated_at": "2025-12-28T19:08:11",
        "execution_mode": "non_as" | "as",
        "settings": {
            "max_rounds": 10,
            "max_files": 100,
            "cwe_type": "327",
            "cwe_output_dir": "/path/to/output",
            "copilot_chat_modification_action": "revert",
            "use_coding_instruction": true,
            "prompt_source_mode": "project"
        },
        "project_list": ["project1", "project2", ...],
        "progress": {
            "current_project_index": 1,
            "current_project_name": "aider__CWE-022__CAL-ALL__M-call",
            "current_round": 10,
            "current_line": 54,
            "current_phase": 1,  # AS Mode: 1=Query, 2=Coding
            "completed_projects": ["ai-hedge-fund__CWE-022__CAL-ALL__M-call"]
        },
        "status": "in_progress" | "completed" | "interrupted"
    }
    """
    
    CHECKPOINT_VERSION = "1.0"
    CHECKPOINT_FILENAME = "execution_checkpoint.json"
    
    def __init__(self, base_dir: str = None):
        """
        Initialize CheckpointManager.
        
        Args:
            base_dir: Base directory for checkpoint storage. 
                      Defaults to workspace/checkpoints/
        """
        if base_dir is None:
            # Default to checkpoints directory in workspace
            workspace = Path(__file__).parent.parent
            base_dir = workspace / "checkpoints"
        
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path = self.base_dir / self.CHECKPOINT_FILENAME
        self._current_checkpoint: Optional[Dict[str, Any]] = None
        
        logger.info(f"CheckpointManager 初始化，存檔路徑: {self.checkpoint_path}")
    
    def create_checkpoint(
        self,
        execution_mode: str,
        project_list: List[str],
        settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a new checkpoint at the start of execution.
        
        Args:
            execution_mode: "non_as" or "as"
            project_list: List of project names to process
            settings: Execution settings dictionary
            
        Returns:
            Created checkpoint dictionary
        """
        now = datetime.now().isoformat()
        
        checkpoint = {
            "version": self.CHECKPOINT_VERSION,
            "created_at": now,
            "updated_at": now,
            "execution_mode": execution_mode,
            "settings": settings,
            "project_list": project_list,
            "progress": {
                "current_project_index": 0,
                "current_project_name": project_list[0] if project_list else None,
                "current_round": 1,
                "current_line": 1,
                "current_phase": 1,  # AS Mode: 1=Query, 2=Coding (Non-AS Mode 始終為 1)
                "completed_projects": [],
                "total_files_processed": 0  # 追蹤已處理的檔案數
            },
            "status": "in_progress"
        }
        
        self._current_checkpoint = checkpoint
        self._save_checkpoint()
        
        logger.info(f"✅ 建立新的執行檢查點 (專案數: {len(project_list)}, 模式: {execution_mode})")
        return checkpoint
    
    def update_progress(
        self,
        project_index: int = None,
        project_name: str = None,
        current_round: int = None,
        current_line: int = None,
        current_phase: int = None,
        completed_project: str = None,
        files_processed_increment: int = None,
        total_files_processed: int = None
    ) -> None:
        """
        Update checkpoint progress during execution.
        
        Args:
            project_index: Current project index (0-based)
            project_name: Current project name
            current_round: Current round number (1-based)
            current_line: Current line number (1-based)
            current_phase: Current phase (AS Mode: 1=Query, 2=Coding; Non-AS: always 1)
            completed_project: Name of project that just completed
            files_processed_increment: Number of files to add to total
            total_files_processed: Set total files processed directly
        """
        if self._current_checkpoint is None:
            logger.warning("無法更新進度: 沒有活動的檢查點")
            return
        
        progress = self._current_checkpoint["progress"]
        
        if project_index is not None:
            progress["current_project_index"] = project_index
        if project_name is not None:
            progress["current_project_name"] = project_name
        if current_round is not None:
            progress["current_round"] = current_round
        if current_line is not None:
            progress["current_line"] = current_line
        if current_phase is not None:
            progress["current_phase"] = current_phase
        if completed_project is not None:
            if completed_project not in progress["completed_projects"]:
                progress["completed_projects"].append(completed_project)
        if files_processed_increment is not None:
            progress["total_files_processed"] = progress.get("total_files_processed", 0) + files_processed_increment
        if total_files_processed is not None:
            progress["total_files_processed"] = total_files_processed
        
        self._current_checkpoint["updated_at"] = datetime.now().isoformat()
        self._save_checkpoint()
    
    def mark_completed(self) -> None:
        """Mark the current execution as completed successfully."""
        if self._current_checkpoint is None:
            return
        
        self._current_checkpoint["status"] = "completed"
        self._current_checkpoint["updated_at"] = datetime.now().isoformat()
        self._save_checkpoint()
        logger.info("✅ 執行已完成，檢查點標記為 completed")
    
    def mark_interrupted(self) -> None:
        """Mark the current execution as interrupted."""
        if self._current_checkpoint is None:
            return
        
        self._current_checkpoint["status"] = "interrupted"
        self._current_checkpoint["updated_at"] = datetime.now().isoformat()
        self._save_checkpoint()
        logger.info("⚠️ 執行已中斷，檢查點標記為 interrupted")
    
    def _save_checkpoint(self) -> None:
        """Save current checkpoint to disk."""
        if self._current_checkpoint is None:
            return
        
        try:
            # Write to temp file first, then rename (atomic operation)
            temp_path = self.checkpoint_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self._current_checkpoint, f, ensure_ascii=False, indent=2)
            temp_path.rename(self.checkpoint_path)
            
            logger.debug(f"檢查點已保存: 專案 {self._current_checkpoint['progress']['current_project_index']}, "
                        f"輪數 {self._current_checkpoint['progress']['current_round']}, "
                        f"Phase {self._current_checkpoint['progress'].get('current_phase', 1)}, "
                        f"行數 {self._current_checkpoint['progress']['current_line']}")
        except Exception as e:
            logger.error(f"保存檢查點失敗: {e}")
    
    def load_checkpoint(self) -> Optional[Dict[str, Any]]:
        """
        Load existing checkpoint from disk.
        
        Returns:
            Checkpoint dictionary if exists and valid, None otherwise
        """
        if not self.checkpoint_path.exists():
            logger.debug("沒有找到現有的檢查點檔案")
            return None
        
        try:
            with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                checkpoint = json.load(f)
            
            # Validate checkpoint version
            if checkpoint.get("version") != self.CHECKPOINT_VERSION:
                logger.warning(f"檢查點版本不相容: {checkpoint.get('version')} != {self.CHECKPOINT_VERSION}")
                return None
            
            self._current_checkpoint = checkpoint
            logger.info(f"✅ 載入現有檢查點 (狀態: {checkpoint['status']})")
            return checkpoint
            
        except Exception as e:
            logger.error(f"載入檢查點失敗: {e}")
            return None
    
    def has_resumable_checkpoint(self) -> bool:
        """
        Check if there's a resumable checkpoint (in_progress or interrupted).
        
        Returns:
            True if resumable checkpoint exists
        """
        checkpoint = self.load_checkpoint()
        if checkpoint is None:
            return False
        
        return checkpoint.get("status") in ("in_progress", "interrupted")
    
    def get_resume_info(self) -> Optional[Dict[str, Any]]:
        """
        Get resume information from existing checkpoint.
        
        Returns:
            Dictionary with resume information or None if no resumable checkpoint
        """
        checkpoint = self.load_checkpoint()
        if checkpoint is None or checkpoint.get("status") == "completed":
            return None
        
        progress = checkpoint["progress"]
        settings = checkpoint["settings"]
        
        # 計算剩餘檔案配額
        max_files = settings.get("max_files", 0)
        files_processed = progress.get("total_files_processed", 0)
        remaining_files = max_files - files_processed if max_files > 0 else 0
        
        return {
            "execution_mode": checkpoint["execution_mode"],
            "project_list": checkpoint["project_list"],
            "settings": settings,
            "resume_from": {
                "project_index": progress["current_project_index"],
                "project_name": progress["current_project_name"],
                "round": progress["current_round"],
                "line": progress["current_line"],
                "phase": progress.get("current_phase", 1)  # AS Mode: 1=Query, 2=Coding
            },
            "completed_projects": progress["completed_projects"],
            "total_projects": len(checkpoint["project_list"]),
            "total_files_processed": files_processed,
            "max_files_limit": max_files,
            "remaining_files_quota": remaining_files,
            "created_at": checkpoint["created_at"],
            "updated_at": checkpoint["updated_at"]
        }
    
    def clear_checkpoint(self) -> None:
        """Remove existing checkpoint file."""
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()
            logger.info("✅ 已清除現有檢查點")
        self._current_checkpoint = None
    
    def detect_progress_from_output(
        self,
        project_list: List[str],
        max_rounds: int,
        output_base_dir: str = None,
        projects_dir: str = None
    ) -> Dict[str, Any]:
        """
        Detect execution progress by analyzing output directories.
        
        This is a fallback method when checkpoint file is unavailable.
        Analyzes ExecutionResult/Success directories to determine completed rounds.
        
        Args:
            project_list: List of project names
            max_rounds: Maximum number of rounds configured
            output_base_dir: Base output directory (defaults to output/ExecutionResult/Success)
            projects_dir: Projects directory (defaults to projects/) for getting expected line counts
            
        Returns:
            Dictionary with detected progress information
        """
        if output_base_dir is None:
            workspace = Path(__file__).parent.parent
            output_base_dir = workspace / "output" / "ExecutionResult" / "Success"
        else:
            output_base_dir = Path(output_base_dir)
        
        if projects_dir is None:
            workspace = Path(__file__).parent.parent
            projects_dir = workspace / "projects"
        else:
            projects_dir = Path(projects_dir)
        
        if not output_base_dir.exists():
            return {
                "completed_projects": [],
                "partially_completed": None,
                "resume_project_index": 0,
                "resume_round": 1,
                "resume_line": 1
            }
        
        completed_projects = []
        partially_completed = None
        resume_project_index = 0
        resume_round = 1
        resume_line = 1
        
        for idx, project_name in enumerate(project_list):
            project_dir = output_base_dir / project_name
            
            if not project_dir.exists():
                # This project hasn't started
                resume_project_index = idx
                break
            
            # Get expected line count from prompt.txt
            prompt_file = projects_dir / project_name / "prompt.txt"
            expected_lines = 0
            if prompt_file.exists():
                try:
                    with open(prompt_file, 'r', encoding='utf-8') as f:
                        expected_lines = len([line for line in f if line.strip()])
                except Exception:
                    pass
            
            # Check which rounds are complete
            completed_rounds = 0
            last_complete_round = 0
            incomplete_round = None
            incomplete_line = None
            
            for round_num in range(1, max_rounds + 1):
                round_dir = project_dir / f"第{round_num}輪"
                if round_dir.exists():
                    # Count files in round directory
                    files = list(round_dir.glob("*.md"))
                    file_count = len(files)
                    
                    if files:
                        # Extract max line number from filenames (format: YYYYMMDD_HHMMSS_第N行.md)
                        max_line = 0
                        for f in files:
                            try:
                                line_part = f.stem.split("_第")[1].replace("行", "")
                                max_line = max(max_line, int(line_part))
                            except (IndexError, ValueError):
                                pass
                        
                        # Check if this round is complete
                        # A round is complete if we have all expected lines
                        if expected_lines > 0 and file_count >= expected_lines:
                            completed_rounds = round_num
                            last_complete_round = round_num
                        elif expected_lines == 0 and file_count > 0:
                            # If we can't determine expected lines, assume round is complete if it has files
                            completed_rounds = round_num
                            last_complete_round = round_num
                        else:
                            # This round is incomplete
                            incomplete_round = round_num
                            incomplete_line = max_line
                            break
                else:
                    # Round doesn't exist - this is where we should resume
                    if incomplete_round is None:
                        incomplete_round = round_num
                        incomplete_line = 0
                    break
            
            # Determine if project is complete
            is_complete = (completed_rounds >= max_rounds) and (incomplete_round is None or incomplete_round > max_rounds)
            
            if is_complete:
                # All rounds complete for this project
                completed_projects.append(project_name)
            else:
                # This project is partially completed
                resume_project_index = idx
                resume_round = incomplete_round if incomplete_round else (last_complete_round + 1)
                resume_line = (incomplete_line + 1) if incomplete_line else 1
                partially_completed = {
                    "project_name": project_name,
                    "expected_lines": expected_lines,
                    "completed_rounds": last_complete_round,
                    "last_round": incomplete_round,
                    "last_line": incomplete_line
                }
                break
        
        result = {
            "completed_projects": completed_projects,
            "partially_completed": partially_completed,
            "resume_project_index": resume_project_index,
            "resume_round": resume_round,
            "resume_line": resume_line
        }
        
        logger.info(f"從輸出目錄偵測進度: {len(completed_projects)} 個專案已完成, "
                   f"繼續從專案 {resume_project_index}, 輪數 {resume_round}, 行數 {resume_line}")
        
        return result
    
    def format_resume_summary(self, resume_info: Dict[str, Any] = None) -> str:
        """
        Format a human-readable summary of resume information.
        
        Args:
            resume_info: Resume information dictionary (from get_resume_info())
            
        Returns:
            Formatted string summary
        """
        if resume_info is None:
            resume_info = self.get_resume_info()
        
        if resume_info is None:
            return "沒有可恢復的執行記錄"
        
        lines = [
            "=" * 60,
            "發現未完成的執行記錄",
            "=" * 60,
            f"執行模式: {'AS Mode (人工自殺模式)' if resume_info['execution_mode'] == 'as' else '非AS Mode (標準模式)'}",
            f"建立時間: {resume_info['created_at']}",
            f"最後更新: {resume_info['updated_at']}",
            "-" * 60,
            f"專案進度: {len(resume_info['completed_projects'])}/{resume_info['total_projects']} 完成",
            f"中斷位置:",
            f"  - 專案: {resume_info['resume_from']['project_name']}",
            f"  - 輪數: 第 {resume_info['resume_from']['round']} 輪",
            f"  - 行數: 第 {resume_info['resume_from']['line']} 行",
            "-" * 60,
            "設定:",
            f"  - 最大輪數: {resume_info['settings'].get('max_rounds', 'N/A')}",
            f"  - 最大檔案數: {resume_info['settings'].get('max_files', 'N/A')}",
            f"  - CWE 類型: CWE-{resume_info['settings'].get('cwe_type', 'N/A')}",
            "=" * 60
        ]
        
        return "\n".join(lines)


def get_checkpoint_manager(base_dir: str = None) -> CheckpointManager:
    """
    Get a singleton CheckpointManager instance.
    
    Args:
        base_dir: Base directory for checkpoint storage
        
    Returns:
        CheckpointManager instance
    """
    return CheckpointManager(base_dir)


# Convenience functions for integration
def save_execution_checkpoint(
    execution_mode: str,
    project_list: List[str],
    settings: Dict[str, Any]
) -> CheckpointManager:
    """
    Create and save a new execution checkpoint.
    
    Args:
        execution_mode: "non_as" or "as"
        project_list: List of project names
        settings: Execution settings
        
    Returns:
        CheckpointManager instance for updating progress
    """
    manager = get_checkpoint_manager()
    manager.create_checkpoint(execution_mode, project_list, settings)
    return manager


def check_for_resumable_execution() -> Optional[Dict[str, Any]]:
    """
    Check if there's a resumable execution and return its info.
    
    Returns:
        Resume information dictionary or None
    """
    manager = get_checkpoint_manager()
    if manager.has_resumable_checkpoint():
        return manager.get_resume_info()
    return None


if __name__ == "__main__":
    # Test code
    print("Testing CheckpointManager...")
    
    # Test create and update
    manager = CheckpointManager("/tmp/test_checkpoints")
    
    projects = ["project1", "project2", "project3"]
    settings = {
        "max_rounds": 10,
        "max_files": 100,
        "cwe_type": "327"
    }
    
    manager.create_checkpoint("non_as", projects, settings)
    
    # Simulate progress
    manager.update_progress(project_index=0, project_name="project1", current_round=1, current_line=5)
    manager.update_progress(current_round=2, current_line=1)
    manager.update_progress(completed_project="project1", project_index=1, project_name="project2", current_round=1, current_line=1)
    
    # Test load
    info = manager.get_resume_info()
    print(manager.format_resume_summary(info))
    
    # Cleanup
    manager.clear_checkpoint()
    print("\n✅ Test completed successfully")
