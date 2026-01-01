# -*- coding: utf-8 -*-
"""
專案選擇器 - 支持 Shift 多選的文件瀏覽器

讓使用者透過簡潔的 UI 選擇要處理的專案。
支持：
- 單擊選擇/取消選擇
- Shift + 單擊範圍選擇
- Ctrl + 單擊多選
- 全選/取消全選
"""

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Set, Tuple, List

from src.logger import get_logger

logger = get_logger("ProjectSelector")


class ProjectSelector:
    """專案選擇器 - 支持 Shift/Ctrl 多選"""
    
    def __init__(self, projects_dir: Path):
        self.projects_dir = projects_dir
        self.selected_projects: Set[str] = set()
        self.all_projects: List[str] = []
        self.cancelled = True
        
        # 創建窗口
        self.root = tk.Tk()
        self.root.title("選擇專案 (已選 0 個)")
        self.root.geometry("700x550")
        
        # 設置窗口位置（居中）
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 700) // 2
        y = (self.root.winfo_screenheight() - 550) // 2
        self.root.geometry(f"700x550+{x}+{y}")
        
        # 設置窗口圖標和樣式
        self.root.resizable(True, True)
        
        self._create_ui()
        self._load_projects()
        
    def _create_ui(self):
        """創建 UI 元素"""
        
        # 頂部標題框
        title_frame = ttk.Frame(self.root, padding="10")
        title_frame.pack(fill=tk.X)
        
        # 標題
        title_label = ttk.Label(
            title_frame,
            text="📁 選擇要處理的專案",
            font=("Arial", 14, "bold")
        )
        title_label.pack(anchor=tk.W)
        
        # 說明
        help_label = ttk.Label(
            title_frame,
            text="• 單擊：選擇/取消  • Shift+單擊：範圍選擇  • Ctrl+單擊：多選",
            foreground="gray",
            font=("Arial", 9)
        )
        help_label.pack(anchor=tk.W, pady=(5, 0))
        
        # 專案列表框架
        list_frame = ttk.Frame(self.root, padding="10 0 10 0")
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        # 列表標籤
        list_label = ttk.Label(list_frame, text="專案列表:", font=("Arial", 10))
        list_label.pack(anchor=tk.W, pady=(0, 5))
        
        # 列表容器（帶滾動條）
        list_container = ttk.Frame(list_frame)
        list_container.pack(fill=tk.BOTH, expand=True)
        
        # 滾動條
        scrollbar = ttk.Scrollbar(list_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Listbox（Extended 模式支持 Shift 和 Ctrl 多選）
        self.listbox = tk.Listbox(
            list_container,
            selectmode=tk.EXTENDED,  # 支持 Shift/Ctrl 多選
            yscrollcommand=scrollbar.set,
            font=("Monospace", 10),
            selectbackground="#0078d4",
            selectforeground="white",
            activestyle="none"
        )
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)
        
        # 綁定選擇事件
        self.listbox.bind('<<ListboxSelect>>', self._on_selection_changed)
        
        # 統計框架
        stats_frame = ttk.Frame(self.root, padding="10")
        stats_frame.pack(fill=tk.X)
        
        self.stats_label = ttk.Label(
            stats_frame,
            text="已選擇 0 個專案",
            font=("Arial", 11, "bold"),
            foreground="#0078d4"
        )
        self.stats_label.pack()
        
        # 按鈕框架
        button_frame = ttk.Frame(self.root, padding="10")
        button_frame.pack(fill=tk.X)
        
        # 左側按鈕（全選/取消全選）
        left_buttons = ttk.Frame(button_frame)
        left_buttons.pack(side=tk.LEFT)
        
        ttk.Button(
            left_buttons,
            text="全選",
            command=self._select_all,
            width=12
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            left_buttons,
            text="取消全選",
            command=self._deselect_all,
            width=12
        ).pack(side=tk.LEFT, padx=5)
        
        # 右側按鈕（確認/取消）
        right_buttons = ttk.Frame(button_frame)
        right_buttons.pack(side=tk.RIGHT)
        
        ttk.Button(
            right_buttons,
            text="✗ 取消",
            command=self._cancel,
            width=12
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            right_buttons,
            text="✓ 確認",
            command=self._confirm,
            width=12
        ).pack(side=tk.LEFT, padx=5)
        
        # 綁定 ESC 和 Enter 鍵
        self.root.bind('<Escape>', lambda e: self._cancel())
        self.root.bind('<Return>', lambda e: self._confirm())
        
    def _load_projects(self):
        """載入專案列表"""
        try:
            if not self.projects_dir.exists():
                logger.error(f"專案目錄不存在: {self.projects_dir}")
                messagebox.showerror(
                    "錯誤",
                    f"專案目錄不存在:\n{self.projects_dir}"
                )
                self._cancel()
                return
            
            # 獲取所有專案目錄
            for item in sorted(self.projects_dir.iterdir()):
                if item.is_dir() and not item.name.startswith('.'):
                    self.all_projects.append(item.name)
                    self.listbox.insert(tk.END, f"  {item.name}")
            
            logger.info(f"載入了 {len(self.all_projects)} 個專案")
            
            if not self.all_projects:
                messagebox.showwarning(
                    "警告",
                    f"在 {self.projects_dir} 中沒有找到任何專案"
                )
                
        except Exception as e:
            logger.error(f"載入專案列表時出錯: {e}", exc_info=True)
            messagebox.showerror("錯誤", f"載入專案列表失敗:\n{str(e)}")
            self._cancel()
    
    def _on_selection_changed(self, event=None):
        """處理選擇變化"""
        try:
            # 獲取當前選中的索引
            selected_indices = self.listbox.curselection()
            
            # 更新選中的專案集合
            self.selected_projects = {
                self.all_projects[i] for i in selected_indices
            }
            
            # 更新統計
            count = len(self.selected_projects)
            self.stats_label.config(text=f"已選擇 {count} 個專案")
            self.root.title(f"選擇專案 (已選 {count} 個)")
            
            logger.debug(f"選擇變化: {count} 個專案")
            
        except Exception as e:
            logger.error(f"處理選擇變化時出錯: {e}", exc_info=True)
    
    def _select_all(self):
        """全選"""
        self.listbox.selection_set(0, tk.END)
        self._on_selection_changed()
        logger.info("全選所有專案")
    
    def _deselect_all(self):
        """取消全選"""
        self.listbox.selection_clear(0, tk.END)
        self._on_selection_changed()
        logger.info("取消全選")
    
    def _confirm(self):
        """確認選擇"""
        try:
            if not self.selected_projects:
                result = messagebox.askyesno(
                    "未選擇專案",
                    "您沒有選擇任何專案，確定要繼續嗎？\n\n"
                    "這將不會處理任何專案。",
                    icon='warning'
                )
                if not result:
                    return
            else:
                # 顯示確認對話框
                project_list = "\n".join(f"  • {name}" for name in sorted(self.selected_projects))
                result = messagebox.askyesno(
                    "確認選擇",
                    f"您選擇了 {len(self.selected_projects)} 個專案：\n\n"
                    f"{project_list}\n\n"
                    f"確認要處理這些專案嗎？\n\n"
                    f"⚠️  將會清除這些專案的執行記錄和結果！",
                    icon='question'
                )
                if not result:
                    return
            
            logger.info(f"確認處理 {len(self.selected_projects)} 個專案")
            self.cancelled = False
            self.root.quit()
            self.root.destroy()
            
        except Exception as e:
            logger.error(f"確認選擇時出錯: {e}", exc_info=True)
            messagebox.showerror("錯誤", f"確認選擇時出錯:\n{str(e)}")
    
    def _cancel(self):
        """取消選擇"""
        logger.info("使用者取消選擇")
        self.selected_projects = set()
        self.cancelled = True
        try:
            self.root.quit()
            self.root.destroy()
        except:
            pass
    
    def show(self) -> Tuple[Set[str], bool, bool]:
        """顯示選擇器並返回結果"""
        try:
            self.root.mainloop()
            return self.selected_projects, True, self.cancelled
        except Exception as e:
            logger.error(f"顯示選擇器時出錯: {e}", exc_info=True)
            return set(), True, True


def show_project_selector(projects_dir: Path = None) -> Tuple[Set[str], bool, bool]:
    """
    顯示專案選擇器（支持 Shift/Ctrl 多選）
    
    Args:
        projects_dir: 專案根目錄路徑
    
    Returns:
        Tuple[Set[str], bool, bool]: (選中的專案集合, 清理歷史=True, 是否取消)
    """
    if projects_dir is None:
        projects_dir = Path(__file__).parent.parent / "projects"
    
    projects_dir = Path(projects_dir).resolve()
    logger.info(f"啟動專案選擇器，專案目錄: {projects_dir}")
    
    try:
        selector = ProjectSelector(projects_dir)
        return selector.show()
    except Exception as e:
        logger.error(f"顯示專案選擇器時出錯: {e}", exc_info=True)
        
        # 顯示錯誤對話框
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("錯誤", f"無法顯示專案選擇器:\n{str(e)}")
        root.destroy()
        
        return set(), True, True


if __name__ == "__main__":
    """測試專案選擇器"""
    print("=" * 60)
    print("專案選擇器測試")
    print("=" * 60)
    
    selected, clean, cancelled = show_project_selector()
    
    print("\n" + "=" * 60)
    if not cancelled:
        print(f"✓ 選中的專案 ({len(selected)} 個):")
        for p in sorted(selected):
            print(f"  • {p}")
        print(f"\n清理歷史: {clean}")
    else:
        print("✗ 已取消")
    print("=" * 60)
