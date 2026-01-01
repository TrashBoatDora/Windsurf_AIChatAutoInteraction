# -*- coding: utf-8 -*-
"""
Copilot Rate Limit Handler - 簡單的回應檢測和重試機制
"""

import time
import re
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))
from src.logger import get_logger


COMPLETION_MARKER = "已完成回答"
COMPLETION_MARKER_en = "Response completed"
REFUSAL_MARKER = "Sorry, I can't assist with that."


def _contains_complete_code(response: str) -> bool:
    """
    檢查回應是否包含完整的代碼
    
    完整代碼的判斷標準：
    1. 包含完整的函數定義（有 def 和 return）
    2. 代碼長度足夠（至少 100 字元）
    
    注意：當只複製代碼塊時，不會包含 ``` 標記，只有純代碼
    
    Args:
        response: 回應內容（可能是純代碼或包含 markdown 的回應）
        
    Returns:
        bool: True = 包含完整代碼
    """
    # 先嘗試從 markdown 代碼塊中提取代碼
    code_block_pattern = r'```(?:python|py)?\s*\n(.*?)```'
    matches = re.findall(code_block_pattern, response, re.DOTALL)
    
    # 如果有 markdown 代碼塊，檢查其中的代碼
    if matches:
        for code_block in matches:
            if _is_complete_python_code(code_block):
                return True
    
    # 如果沒有 markdown 標記，直接檢查整個回應是否為完整代碼
    # （這是複製代碼塊按鈕時的情況）
    if _is_complete_python_code(response):
        return True
    
    return False


def _is_complete_python_code(code: str) -> bool:
    """
    檢查是否為完整的 Python 代碼
    
    完整代碼的判斷標準（滿足任一即可）：
    1. 有函數定義 (def) 且有 return 語句
    2. 有函數定義 (def) 且有 docstring（三引號）
    3. 代碼足夠長（≥200 字元）且包含 import
    
    Args:
        code: 代碼內容
        
    Returns:
        bool: True = 完整的 Python 代碼
    """
    code = code.strip()
    
    # 最小長度檢查（太短的代碼片段不算完整）
    if len(code) < 80:
        return False
    
    has_def = 'def ' in code
    has_return = 'return ' in code
    has_docstring = '"""' in code or "'''" in code
    has_import = 'import ' in code
    
    # 有函數定義且有 return，視為完整
    if has_def and has_return:
        return True
    
    # 有函數定義且有 docstring，視為完整（函數可能沒有顯式 return）
    if has_def and has_docstring:
        return True
    
    # 代碼足夠長且包含 import，可能是完整的代碼片段
    if len(code) >= 200 and has_import:
        return True
    
    # 有函數定義且代碼足夠長（≥150 字元），視為完整
    if has_def and len(code) >= 150:
        return True
    
    return False


def is_response_incomplete(response: str) -> bool:
    """
    檢查回應是否完成。
    
    完成判斷邏輯（按優先順序）：
    1. 包含完成標記（「已完成回答」或「Response completed」）→ 完成
    2. 包含拒絕回應標記 → 完成
    3. 包含完整的代碼塊（有 def + return，且長度足夠）→ 完成
    4. 其他情況 → 不完整
    
    Args:
        response: 原始回應內容
        
    Returns:
        bool: True = 不完整（需要重試），False = 完整（可以繼續）
    """
    if not response:
        return True

    # 只要回應中包含完成標記，就算完成
    if COMPLETION_MARKER in response or COMPLETION_MARKER_en in response:
        return False
    
    # 如果回應包含 Copilot 的拒絕回應，也視為完成
    if REFUSAL_MARKER in response:
        return False
    
    # 檢查是否包含完整的代碼（針對只複製到代碼塊的情況）
    if _contains_complete_code(response):
        return False

    return True


def wait_and_retry(seconds: int, line_number: int, round_number: int, logger, retry_count: int = 0):
    """
    等待指定時間並顯示倒數（改良版指數退避策略）
    
    Args:
        seconds: 基礎等待秒數（已廢棄，改用 retry_count 計算）
        line_number: 提示詞行號
        round_number: 互動輪數
        logger: 日誌記錄器
        retry_count: 當前是第幾次重試（0開始）
        
    Note:
        改良版指數退避策略：每個時間階段重複一次，最大上限 2160 秒
        - retry_count=0,1: 10秒
        - retry_count=2,3: 60秒
        - retry_count=4,5: 360秒（6分鐘）
        - retry_count=6,7,8,9: 2160秒（36分鐘，達到上限）
        
        計算公式：
        1. 計算階段：stage = retry_count // 2
        2. 計算基礎時間：base_time = 10 * (6 ^ stage)
        3. 應用上限：min(base_time, 2160)
    """
    # 改良版指數退避策略：每個階段重複一次，並設置上限
    stage = retry_count // 2  # 每兩次重試進入下一個階段
    base_time = 10 * (6 ** stage)
    actual_wait_seconds = min(base_time, 2160)  # 最大等待時間為 2160 秒
    
    logger.warning(f"⏳ 回應不完整，等待 {actual_wait_seconds} 秒後重試 [輪次: {round_number}, 行號: {line_number}, 重試次數: {retry_count + 1}]")
    logger.info(f"   📊 改良版指數退避策略: stage={stage}, 10 × 6^{stage} = {base_time} 秒 → 實際等待 {actual_wait_seconds} 秒")
    
    # 每60秒顯示一次進度
    remaining = actual_wait_seconds
    while remaining > 0:
        chunk = min(60, remaining)
        if remaining == actual_wait_seconds:
            logger.info(f"   開始等待 {actual_wait_seconds} 秒...")
        else:
            minutes = remaining // 60
            secs = remaining % 60
            if minutes > 0:
                logger.info(f"   剩餘 {minutes} 分 {secs} 秒...")
            else:
                logger.info(f"   剩餘 {remaining} 秒...")
        time.sleep(chunk)
        remaining -= chunk
    
    logger.info(f"   ✓ 等待完成，準備第 {retry_count + 1} 次重試")
