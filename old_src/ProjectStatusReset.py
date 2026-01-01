import json
import shutil
from pathlib import Path
import os

status_file = Path('projects/automation_status.json')
script_root = Path(__file__).parent.parent  # 腳本根目錄
execution_result_dir = script_root / "ExecutionResult"

# 刪除舊的 automation_report 文件
projects_dir = Path('projects')
if projects_dir.exists():
    for file in projects_dir.glob("automation_report_*.json"):
        try:
            file.unlink()
            print(f"已刪除舊的報告文件: {file}")
        except Exception as e:
            print(f"刪除 {file} 失敗: {e}")

# 刪除 automation_status.json
if status_file.exists():
    try:
        status_file.unlink()
        print(f"已刪除狀態檔案: {status_file}")
    except Exception as e:
        print(f"刪除 {status_file} 失敗: {e}")

# 刪除統一的 ExecutionResult 資料夾
if execution_result_dir.exists():
    try:
        shutil.rmtree(execution_result_dir)
        print(f"已刪除統一的 ExecutionResult 資料夾: {execution_result_dir}")
    except Exception as e:
        print(f"刪除 {execution_result_dir} 失敗: {e}")

# 清理專案目錄中的舊檔案（向後相容）
projects_root = Path('projects')
if projects_root.exists():
    for project_dir in projects_root.iterdir():
        if project_dir.is_dir() and project_dir.name != '__pycache__':
            # 清理專案目錄中的舊檔案
            for fname in ["Copilot_AutoComplete.txt", "Copilot_AutoComplete.md", "Copilot_AutoComplete.report", "automation_log.txt"]:
                fpath = project_dir / fname
                if fpath.exists():
                    try:
                        fpath.unlink()
                        print(f"已刪除 {fpath}")
                    except Exception as e:
                        print(f"刪除 {fpath} 失敗: {e}")
            
            # 刪除專案內的舊 ExecutionResult 資料夾（向後相容）
            old_execution_result = project_dir / "ExecutionResult"
            if old_execution_result.exists():
                try:
                    shutil.rmtree(old_execution_result)
                    print(f"已刪除 {old_execution_result}")
                except Exception as e:
                    print(f"刪除 {old_execution_result} 失敗: {e}")

# -----------------------------------------------------------------------------
# 新增：清除 logs 資料夾下的全部檔案與子資料夾（保留 logs 資料夾本身）
# -----------------------------------------------------------------------------
logs_dir = Path('logs')
if logs_dir.exists() and logs_dir.is_dir():
    for entry in logs_dir.iterdir():
        try:
            if entry.is_file() or entry.is_symlink():
                entry.unlink()
                print(f"已刪除檔案: {entry}")
            elif entry.is_dir():
                shutil.rmtree(entry)
                print(f"已刪除資料夾: {entry}")
        except Exception as e:
            print(f"刪除 {entry} 失敗: {e}")

print('✅ 所有專案狀態和結果檔案已完全清除')
