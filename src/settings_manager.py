# -*- coding: utf-8 -*-
"""
Hybrid UI Automation Script - 設定管理模組
統一管理所有設定檔案的讀取和寫入
"""

import json
from pathlib import Path
from typing import Dict, Any
from config.config import config

class SettingsManager:
    """統一設定管理器"""
    
    def __init__(self):
        self.settings_file = config.PROJECT_ROOT / "config" / "settings.json"
        self._cache = None
    
    def load_settings(self) -> Dict[str, Any]:
        """載入完整設定"""
        if self._cache is not None:
            return self._cache
            
        default_settings = {
            "version": "1.0.0",
            "description": "Hybrid UI Automation Script Configuration",
            "settings": {
                "automation": {
                    "max_retry_attempts": 3,
                    "emergency_stop_enabled": True
                },
                "vscode": {
                    "startup_delay_seconds": 15,
                    "command_delay_seconds": 2,
                    "copilot_chat_hotkey": ["ctrl", "alt", "i"],
                    "ui_reset_on_start": True
                },
                "copilot": {
                    "response_timeout_seconds": 300,
                    "check_interval_seconds": 5,
                    "prompt_template": "請幫我分析所有 Python、C、C++、Go、Java 檔案，並且自動幫我寫上你認為需要補的code，並把你寫了哪些檔案的哪幾行及程式碼，增加至一個Copilot_AutoComplete.txt中。"
                },
                "interaction": {
                    "enabled": True,
                    "max_rounds": 1,
                    "include_previous_response": False,
                    "round_delay": 2,
                    "show_ui_on_startup": True
                },
                "image_recognition": {
                    "confidence_threshold": 0.9,
                    "screenshot_delay_seconds": 0.5,
                    "required_images": [
                        "regenerate_button.png",
                        "copy_button.png", 
                        "copilot_input.png"
                    ]
                },
                "logging": {
                    "level": "INFO",
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    "file_prefix": "automation_",
                    "console_output": True
                }
            }
        }
        
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                    # 深度合併設定
                    self._deep_merge(default_settings, loaded_settings)
            except Exception as e:
                print(f"載入設定時發生錯誤: {e}")
        
        self._cache = default_settings
        return default_settings
    
    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """儲存設定到檔案"""
        try:
            # 確保目錄存在
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
            
            # 清除快取
            self._cache = None
            return True
        except Exception as e:
            print(f"儲存設定時發生錯誤: {e}")
            return False
    
    def get_interaction_settings(self) -> Dict[str, Any]:
        """取得互動設定"""
        settings = self.load_settings()
        return settings.get("settings", {}).get("interaction", {})
    
    def update_interaction_settings(self, interaction_settings: Dict[str, Any]) -> bool:
        """更新互動設定"""
        settings = self.load_settings()
        if "settings" not in settings:
            settings["settings"] = {}
        settings["settings"]["interaction"] = interaction_settings
        return self.save_settings(settings)
    
    def _deep_merge(self, base: Dict, update: Dict):
        """深度合併字典"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

# 全域設定管理器實例
settings_manager = SettingsManager()