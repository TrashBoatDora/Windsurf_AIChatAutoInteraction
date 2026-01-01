# -*- coding: utf-8 -*-
"""
Hybrid UI Automation Script - 互動設定介面
提供使用者友善的設定介面，讓使用者選擇多輪互動的相關設定
"""

import tkinter as tk
from tkinter import ttk, messagebox
import json
import sys
from pathlib import Path

# 設定模組搜尋路徑
sys.path.append(str(Path(__file__).parent.parent))
try:
    from config.config import config
except ImportError:
    try:
        from config import config
    except ImportError:
        import sys
        sys.path.append(str(Path(__file__).parent.parent / "config"))
        import config

class InteractionSettingsUI:
    """多輪互動設定介面"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Copilot Chat 多輪互動設定")
        self.root.geometry("333x433")  # 調整視窗高度
        self.root.resizable(True, True)  # 允許調整大小
        
        # 設定關閉事件處理
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.cancelled = False  # 追蹤是否被取消
        
        # 載入現有設定
        self.settings = self.load_settings()
        
        # 建立 UI
        self.create_widgets()
        
    def load_settings(self):
        """載入設定檔案"""
        # 導入設定管理器
        try:
            from src.settings_manager import settings_manager
        except ImportError:
            # 如果從 src 目錄內執行，直接導入
            from settings_manager import settings_manager
        
        interaction_settings = settings_manager.get_interaction_settings()
        
        # 轉換為 UI 期望的格式
        return {
            "interaction_enabled": interaction_settings.get("enabled", config.INTERACTION_ENABLED),
            "max_rounds": interaction_settings.get("max_rounds", config.INTERACTION_MAX_ROUNDS),
            "include_previous_response": interaction_settings.get("include_previous_response", config.INTERACTION_INCLUDE_PREVIOUS_RESPONSE),
            "round_delay": interaction_settings.get("round_delay", config.INTERACTION_ROUND_DELAY),
            "copilot_chat_modification_action": interaction_settings.get("copilot_chat_modification_action", config.COPILOT_CHAT_MODIFICATION_ACTION),
            "prompt_source_mode": interaction_settings.get("prompt_source_mode", config.PROMPT_SOURCE_MODE),  # 提示詞來源模式
            "use_coding_instruction": interaction_settings.get("use_coding_instruction", False)  # Coding Instruction 模板
        }
    
    def create_scrollable_frame(self):
        """創建可滾動的框架"""
        # 創建 Canvas 和 Scrollbar
        self.canvas = tk.Canvas(self.root, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        # 設定 Canvas 滾動
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        # 在 Canvas 中創建視窗
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        # 配置滾輪綁定
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # 綁定滾輪事件
        self.bind_mousewheel()
        
        # 配置 Canvas 尺寸調整
        self.canvas.bind('<Configure>', self.on_canvas_configure)
        
        # 放置 Canvas 和 Scrollbar（留出底部按鈕空間）
        self.canvas.pack(side="left", fill="both", expand=True, padx=(20, 0), pady=(10, 20))
        self.scrollbar.pack(side="right", fill="y", padx=(0, 20), pady=(10, 20))
    
    def on_canvas_configure(self, event):
        """Canvas 尺寸改變時調整滾動區域"""
        # 更新 scrollable_frame 的寬度以匹配 canvas 寬度
        canvas_width = event.width
        self.canvas.itemconfig(self.canvas_window, width=canvas_width)
    
    def bind_mousewheel(self):
        """綁定滑鼠滾輪事件"""
        # 為 Canvas 綁定滾輪事件
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.scrollable_frame.bind("<MouseWheel>", self.on_mousewheel)
        self.root.bind("<MouseWheel>", self.on_mousewheel)
        
        # 遞迴綁定所有子元件
        self.bind_mousewheel_to_children(self.scrollable_frame)
    
    def bind_mousewheel_to_children(self, parent):
        """遞迴為所有子元件綁定滾輪事件"""
        for child in parent.winfo_children():
            try:
                child.bind("<MouseWheel>", self.on_mousewheel)
                # 遞迴處理子元件的子元件
                if hasattr(child, 'winfo_children'):
                    self.bind_mousewheel_to_children(child)
            except:
                pass  # 某些元件可能不支援事件綁定
    
    def on_mousewheel(self, event):
        """滑鼠滾輪事件處理"""
        try:
            # Windows 系統的滾輪事件處理
            if event.delta:
                delta = -1 * (event.delta / 120)
            else:
                # Linux/Mac 系統的滾輪事件處理
                delta = -1 if event.num == 4 else 1
            
            # 執行滾動
            self.canvas.yview_scroll(int(delta), "units")
            
            # 阻止事件繼續傳播
            return "break"
        except:
            pass
    
    def save_settings(self):
        """儲存設定到檔案"""
        try:
            # 導入設定管理器
            try:
                from src.settings_manager import settings_manager
            except ImportError:
                # 如果從 src 目錄內執行，直接導入
                from settings_manager import settings_manager
            
            # 轉換為統一設定格式
            interaction_settings = {
                "enabled": self.settings["interaction_enabled"],
                "max_rounds": self.settings["max_rounds"],
                "include_previous_response": self.settings["include_previous_response"],
                "round_delay": self.settings["round_delay"],
                "show_ui_on_startup": True,
                "copilot_chat_modification_action": self.settings["copilot_chat_modification_action"],
                "prompt_source_mode": self.settings["prompt_source_mode"],  # 提示詞來源模式
                "use_coding_instruction": self.settings.get("use_coding_instruction", False)  # Coding Instruction 模板
            }
            
            return settings_manager.update_interaction_settings(interaction_settings)
        except Exception as e:
            print(f"儲存設定時發生錯誤: {e}")
            return False
    
    def create_widgets(self):
        """建立 UI 元件"""
        # 主標題
        title_label = tk.Label(
            self.root, 
            text="選擇多輪互動模式", 
            font=("Arial", 12, "bold")  # 縮小字體
        )
        title_label.pack(pady=15)
        
        # 副標題
        subtitle_label = tk.Label(
            self.root, 
            text="請選擇本次執行的互動設定", 
            font=("Arial", 8),  # 縮小字體
            fg="gray"
        )
        subtitle_label.pack(pady=(0, 15))
        
        # 創建固定在底部的按鈕框架（先創建，確保在最底部）
        self.create_bottom_buttons()
        
        # 創建可滾動的主容器（留出底部按鈕空間）
        self.create_scrollable_frame()
        
        # 主要設定框架（放在可滾動容器內）
        main_frame = ttk.Frame(self.scrollable_frame)
        main_frame.pack(padx=20, pady=10, fill="both", expand=True)
        
        # 啟用多輪互動
        self.interaction_enabled_var = tk.BooleanVar(
            value=self.settings["interaction_enabled"]
        )
        interaction_checkbox = ttk.Checkbutton(
            main_frame,
            text="啟用多輪互動功能",
            variable=self.interaction_enabled_var,
            command=self.on_interaction_enabled_changed
        )
        interaction_checkbox.pack(anchor="w", pady=5)
        
        # 互動設定框架
        self.interaction_frame = ttk.LabelFrame(main_frame, text="互動設定")
        self.interaction_frame.pack(fill="x", pady=10)
        
        # 最大輪數設定
        rounds_frame = ttk.Frame(self.interaction_frame)
        rounds_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(rounds_frame, text="最大互動輪數:").pack(side="left")
        self.max_rounds_var = tk.IntVar(value=self.settings["max_rounds"])
        rounds_spinbox = ttk.Spinbox(
            rounds_frame,
            from_=1,
            to=10,
            textvariable=self.max_rounds_var,
            width=5
        )
        rounds_spinbox.pack(side="right")
        
        # 提示詞來源設定框架
        prompt_source_frame = ttk.LabelFrame(main_frame, text="提示詞來源設定")
        prompt_source_frame.pack(fill="x", pady=10)
        
        # 提示詞來源選項
        prompt_source_option_frame = ttk.Frame(prompt_source_frame)
        prompt_source_option_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(prompt_source_option_frame, text="選擇提示詞來源:").pack(anchor="w", pady=(5, 2))
        
        self.prompt_source_var = tk.StringVar(
            value=self.settings["prompt_source_mode"]
        )
        
        # 全域提示詞選項
        global_prompt_radio = ttk.Radiobutton(
            prompt_source_option_frame,
            text="使用全域提示詞 (prompts/prompt1.txt & prompt2.txt)",
            variable=self.prompt_source_var,
            value="global",
            command=self.on_prompt_source_changed
        )
        global_prompt_radio.pack(anchor="w", padx=20, pady=2)
        
        # 專案專用提示詞選項
        project_prompt_radio = ttk.Radiobutton(
            prompt_source_option_frame,
            text="使用專案專用提示詞 (各專案目錄下的 prompt.txt)",
            variable=self.prompt_source_var,
            value="project",
            command=self.on_prompt_source_changed
        )
        project_prompt_radio.pack(anchor="w", padx=20, pady=2)
        
        # 提示詞來源說明
        self.prompt_source_explanation_text = tk.Text(
            prompt_source_frame,
            height=4,
            width=40,  # 縮小寬度
            wrap="word",
            state="disabled",
            bg=self.root.cget("bg"),
            font=("Arial", 7)  # 縮小字體
        )
        self.prompt_source_explanation_text.pack(padx=10, pady=5, fill="x")
        
        # 更新說明內容
        self.update_prompt_source_explanation()
        
        # === Coding Instruction 模板選項（僅在專案模式下可用）===
        self.coding_instruction_frame = ttk.Frame(prompt_source_frame)
        self.coding_instruction_frame.pack(fill="x", padx=10, pady=5)
        
        self.use_coding_instruction_var = tk.BooleanVar(
            value=self.settings.get("use_coding_instruction", False)
        )
        
        self.coding_instruction_checkbox = ttk.Checkbutton(
            self.coding_instruction_frame,
            text="使用 Coding Instruction 模板（解析 prompt.txt 並套用 coding_instruction.txt）",
            variable=self.use_coding_instruction_var
        )
        self.coding_instruction_checkbox.pack(anchor="w", pady=2)
        
        # Coding Instruction 說明
        coding_instruction_explanation_text = tk.Text(
            self.coding_instruction_frame,
            height=3,
            width=40,  # 縮小寬度
            wrap="word",
            state="disabled",
            bg=self.root.cget("bg"),
            font=("Arial", 7)  # 縮小字體
        )
        coding_instruction_explanation_text.pack(padx=20, pady=2, fill="x")
        
        coding_instruction_explanation = """說明：
• 啟用時：解析 prompt.txt 每行（格式：filepath|function1()、function2()），只取第一個函式
• 將檔案路徑和函式名稱套用到 assets/prompt-template/coding_instruction.txt 模板中發送
• 適合需要統一格式的程式碼生成任務"""
        
        coding_instruction_explanation_text.config(state="normal")
        coding_instruction_explanation_text.insert("1.0", coding_instruction_explanation)
        coding_instruction_explanation_text.config(state="disabled")
        
        # 根據初始的 prompt_source_mode 設定是否啟用 Coding Instruction 選項
        self.update_coding_instruction_state()
        
        # 回應串接設定框架
        chaining_frame = ttk.LabelFrame(main_frame, text="回應串接設定")
        chaining_frame.pack(fill="x", pady=10)
        
        # 啟用回應串接
        self.include_previous_var = tk.BooleanVar(
            value=self.settings["include_previous_response"]
        )
        chaining_checkbox = ttk.Checkbutton(
            chaining_frame,
            text="在新一輪提示詞中包含上一輪 Copilot 回應",
            variable=self.include_previous_var
        )
        chaining_checkbox.pack(anchor="w", padx=10, pady=5)
        
        # 說明文字
        explanation_text = tk.Text(
            chaining_frame,
            height=5,  # 增加高度
            width=40,  # 縮小寬度
            wrap="word",
            state="disabled",
            bg=self.root.cget("bg"),
            font=("Arial", 7)  # 縮小字體  # 設定字體
        )
        explanation_text.pack(padx=10, pady=5, fill="x")
        
        explanation_content = """說明：
• 啟用時：每一輪會將上一輪的 Copilot 回應內容加入新的提示詞中，形成連續對話
• 停用時：每一輪都只使用原始的 prompt.txt 內容，進行獨立分析
• 建議在需要連續對話脈絡時啟用，單純重複分析時停用
• 此設定僅適用於本次執行，下次執行時會再次詢問
• 輪次間會自動使用預設間隔時間"""
        
        explanation_text.config(state="normal")
        explanation_text.insert("1.0", explanation_content)
        explanation_text.config(state="disabled")
        
        # CopilotChat 修改結果處理設定框架
        modification_frame = ttk.LabelFrame(main_frame, text="CopilotChat 修改結果處理")
        modification_frame.pack(fill="x", pady=10)
        
        # 修改結果處理選項
        modification_action_frame = ttk.Frame(modification_frame)
        modification_action_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(modification_action_frame, text="當 Copilot 修改代碼時:").pack(anchor="w", pady=(5, 2))
        
        self.modification_action_var = tk.StringVar(
            value=self.settings["copilot_chat_modification_action"]
        )
        
        # 保留選項
        keep_radio = ttk.Radiobutton(
            modification_action_frame,
            text="保留修改 (按 Enter)",
            variable=self.modification_action_var,
            value="keep"
        )
        keep_radio.pack(anchor="w", padx=20, pady=2)
        
        # 復原選項
        revert_radio = ttk.Radiobutton(
            modification_action_frame,
            text="復原修改 (按右鍵 + Enter)",
            variable=self.modification_action_var,
            value="revert"
        )
        revert_radio.pack(anchor="w", padx=20, pady=2)
        
        # 修改結果處理說明
        modification_explanation_text = tk.Text(
            modification_frame,
            height=3,
            width=40,  # 縮小寬度
            wrap="word",
            state="disabled",
            bg=self.root.cget("bg"),
            font=("Arial", 7)  # 縮小字體
        )
        modification_explanation_text.pack(padx=10, pady=5, fill="x")
        
        modification_explanation_content = """說明：
• 保留修改：當 Copilot 修改代碼並提示保存時，自動選擇保留修改
• 復原修改：當 Copilot 修改代碼並提示保存時，自動選擇復原修改"""
        
        modification_explanation_text.config(state="normal")
        modification_explanation_text.insert("1.0", modification_explanation_content)
        modification_explanation_text.config(state="disabled")
        
        # 初始狀態設定
        self.on_interaction_enabled_changed()
        
        # 更新滾輪綁定（在所有元件創建完成後）
        self.root.after(100, self.bind_mousewheel)
        
        # 確保 Canvas 可以獲得焦點以響應滾輪事件
        self.canvas.focus_set()
    
    def create_bottom_buttons(self):
        """創建固定在底部的按鈕"""
        # 按鈕框架（固定在主視窗底部）
        button_frame = ttk.Frame(self.root)
        button_frame.pack(side="bottom", fill="x", padx=20, pady=15)
        
        # 按鈕容器（居中排列）
        buttons_container = ttk.Frame(button_frame)
        buttons_container.pack(expand=True)
        
        # 取消按鈕
        cancel_button = ttk.Button(
            buttons_container,
            text="取消",
            command=self.on_close,
            width=12
        )
        cancel_button.pack(side="left", padx=10)
        
        # 確定按鈕
        save_button = ttk.Button(
            buttons_container,
            text="確定執行",
            command=self.save_and_close,
            width=12
        )
        save_button.pack(side="right", padx=10)
    
    def on_close(self):
        """處理視窗關閉事件"""
        # 標記為取消並關閉視窗
        print("使用者關閉設定視窗")
        self.cancelled = True
        self.root.destroy()
    
    def on_interaction_enabled_changed(self):
        """當啟用多輪互動選項改變時"""
        enabled = self.interaction_enabled_var.get()
        
        # 啟用或停用相關元件
        for child in self.interaction_frame.winfo_children():
            self.set_widget_state(child, "normal" if enabled else "disabled")
    
    def set_widget_state(self, widget, state):
        """設定元件狀態"""
        try:
            widget.configure(state=state)
        except tk.TclError:
            # 某些元件可能不支援 state 屬性
            pass
        
        # 遞迴處理子元件
        for child in widget.winfo_children():
            self.set_widget_state(child, state)
    

    def save_and_close(self):
        """更新設定並關閉視窗（不保存到檔案）"""
        # 更新設定
        self.settings["interaction_enabled"] = self.interaction_enabled_var.get()
        self.settings["max_rounds"] = self.max_rounds_var.get()
        self.settings["include_previous_response"] = self.include_previous_var.get()
        self.settings["round_delay"] = config.INTERACTION_ROUND_DELAY  # 使用預設值
        self.settings["copilot_chat_modification_action"] = self.modification_action_var.get()
        self.settings["prompt_source_mode"] = self.prompt_source_var.get()
        self.settings["use_coding_instruction"] = self.use_coding_instruction_var.get()  # 新增
        
        # 如果選擇專案模式，需要再次驗證所有專案都有提示詞
        if self.settings["prompt_source_mode"] == "project":
            try:
                try:
                    from src.project_manager import project_manager
                except ImportError:
                    from project_manager import project_manager
                project_manager.scan_projects()
                all_valid, missing_projects = project_manager.validate_projects_for_custom_prompts()
                
                if not all_valid:
                    error_msg = f"無法使用專案專用提示詞模式！\n\n"
                    error_msg += f"以下專案缺少 prompt.txt：\n"
                    error_msg += "\n".join(f"• {project}" for project in missing_projects)
                    error_msg += f"\n\n程式將中止執行。"
                    
                    messagebox.showerror("專案驗證失敗", error_msg)
                    return  # 不關閉視窗，讓使用者重新選擇
            except Exception as e:
                messagebox.showerror("驗證錯誤", f"驗證專案時發生錯誤：\n{str(e)}")
                return  # 不關閉視窗
        
        # 直接關閉視窗，開始執行腳本
        self.root.destroy()
    
    def on_prompt_source_changed(self):
        """當提示詞來源選項改變時"""
        self.update_prompt_source_explanation()
        self.update_coding_instruction_state()  # 更新 Coding Instruction 選項的可用狀態
        
        # 如果選擇專案專用提示詞，需要驗證專案是否都有 prompt.txt
        if self.prompt_source_var.get() == "project":
            self.validate_project_prompts()
    
    def update_coding_instruction_state(self):
        """根據 prompt_source_mode 更新 Coding Instruction 選項的啟用狀態"""
        if self.prompt_source_var.get() == "project":
            # 專案模式：啟用 Coding Instruction 選項
            self.coding_instruction_checkbox.config(state="normal")
        else:
            # 全域模式：停用 Coding Instruction 選項並取消勾選
            self.coding_instruction_checkbox.config(state="disabled")
            self.use_coding_instruction_var.set(False)
    
    def update_prompt_source_explanation(self):
        """更新提示詞來源說明"""
        mode = self.prompt_source_var.get()
        
        if mode == "global":
            explanation = """全域提示詞模式：
• 第1輪使用 prompts/prompt1.txt
• 第2輪及後續使用 prompts/prompt2.txt
• 所有專案使用相同的提示詞內容
• 適合批次處理相同類型的分析任務"""
        else:
            explanation = """專案專用提示詞模式：
• 每個專案使用各自目錄下的 prompt.txt
• 每輪會逐行發送專案的 prompt.txt 內容
• 如有專案缺少 prompt.txt，程式將中止運行
• 適合需要個別化分析的專案"""
        
        self.prompt_source_explanation_text.config(state="normal")
        self.prompt_source_explanation_text.delete("1.0", "end")
        self.prompt_source_explanation_text.insert("1.0", explanation)
        self.prompt_source_explanation_text.config(state="disabled")
    
    def validate_project_prompts(self):
        """驗證專案是否都有 prompt.txt"""
        try:
            # 導入專案管理器
            try:
                from src.project_manager import project_manager
            except ImportError:
                from project_manager import project_manager
            
            # 掃描專案
            project_manager.scan_projects()
            
            # 驗證提示詞
            all_valid, missing_projects = project_manager.validate_projects_for_custom_prompts()
            
            if not all_valid:
                error_msg = f"以下專案缺少 prompt.txt 檔案：\n"
                error_msg += "\n".join(f"• {project}" for project in missing_projects)
                error_msg += "\n\n請為這些專案新增 prompt.txt 或選擇全域提示詞模式。"
                
                messagebox.showerror("提示詞檔案缺失", error_msg)
                
                # 自動切回全域模式
                self.prompt_source_var.set("global")
                self.update_prompt_source_explanation()
                
            else:
                # 顯示專案摘要資訊
                summary = project_manager.get_project_prompt_summary()
                info_msg = f"專案提示詞驗證通過！\n\n"
                info_msg += f"📊 摘要統計：\n"
                info_msg += f"• 總專案數：{summary['total_projects']}\n"
                info_msg += f"• 有提示詞的專案：{summary['projects_with_prompts']}\n"
                info_msg += f"• 總提示詞行數：{summary['total_prompt_lines']}\n"
                
                messagebox.showinfo("專案驗證結果", info_msg)
        
        except Exception as e:
            messagebox.showerror("驗證錯誤", f"驗證專案提示詞時發生錯誤：\n{str(e)}")
    
    def run(self):
        """顯示設定介面"""
        self.root.mainloop()
        
        # 如果使用者按 X 取消，回傳 None 表示取消
        if self.cancelled:
            return None
        
        return self.settings

def show_interaction_settings():
    """顯示互動設定介面並回傳設定，如果取消則回傳 None"""
    ui = InteractionSettingsUI()
    return ui.run()

if __name__ == "__main__":
    print("=== Copilot Chat 多輪互動設定 ===")
    print("啟動設定介面...")
    
    try:
        settings = show_interaction_settings()
        if settings is None:
            print("\n設定已取消。")
        else:
            print("\n設定完成！")
            print(f"最終設定: {settings}")
    except Exception as e:
        print(f"設定過程中發生錯誤: {e}")
        input("按 Enter 鍵結束...")
    
    print("設定程式結束。")