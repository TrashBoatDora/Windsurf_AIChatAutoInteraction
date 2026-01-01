#!/bin/bash
# Python 3.10.12 環境啟動腳本
# 
# 使用方式:
#   source activate_env.sh
#
# 或在 .bashrc 中添加:
#   alias activate_copilot='source /path/to/VSCode_CopilotAutoInteraction/activate_env.sh'

echo "=========================================="
echo "正在啟動 Copilot Auto Interaction 環境"
echo "=========================================="

# 自動偵測 conda 路徑
if [ -f ~/anaconda3/etc/profile.d/conda.sh ]; then
    source ~/anaconda3/etc/profile.d/conda.sh
elif [ -f ~/miniconda3/etc/profile.d/conda.sh ]; then
    source ~/miniconda3/etc/profile.d/conda.sh
elif [ -f /opt/conda/etc/profile.d/conda.sh ]; then
    source /opt/conda/etc/profile.d/conda.sh
else
    # 嘗試使用 conda info 取得路徑
    CONDA_BASE=$(conda info --base 2>/dev/null)
    if [ -n "$CONDA_BASE" ] && [ -f "${CONDA_BASE}/etc/profile.d/conda.sh" ]; then
        source "${CONDA_BASE}/etc/profile.d/conda.sh"
    else
        echo "❌ 錯誤: 找不到 conda 初始化腳本"
        echo "請確認已安裝 Anaconda 或 Miniconda"
        return 1 2>/dev/null || exit 1
    fi
fi

# 啟動 Python 3.10.12 環境
conda activate copilot_py310

# 顯示環境資訊
echo ""
echo "✅ 環境已啟動"
echo ""
echo "📌 環境資訊:"
echo "   - Python:  $(python --version)"
echo "   - Bandit:  $(bandit --version | head -n1)"
echo "   - Semgrep: $(semgrep --version)"
echo "   - Conda 環境: copilot_py310"

# Linux 系統依賴檢查
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo ""
    echo "📌 系統依賴檢查:"
    
    MISSING_DEPS=""
    
    # 檢查 gnome-screenshot (PyAutoGUI 截圖必需)
    if command -v gnome-screenshot &> /dev/null; then
        echo "   - gnome-screenshot: ✅"
    else
        echo "   - gnome-screenshot: ❌ (截圖功能必需)"
        MISSING_DEPS="$MISSING_DEPS gnome-screenshot"
    fi
    
    # 檢查 scrot (備用截圖工具)
    if command -v scrot &> /dev/null; then
        echo "   - scrot: ✅"
    else
        echo "   - scrot: ⚠️ (備用截圖工具)"
        MISSING_DEPS="$MISSING_DEPS scrot"
    fi
    
    # 檢查剪貼簿工具
    if command -v xclip &> /dev/null || command -v xsel &> /dev/null; then
        echo "   - 剪貼簿工具: ✅"
    else
        echo "   - 剪貼簿工具: ❌ (xclip/xsel)"
        MISSING_DEPS="$MISSING_DEPS xclip"
    fi
    
    if [ -n "$MISSING_DEPS" ]; then
        echo ""
        echo "⚠️  缺少系統依賴，請執行以下命令安裝:"
        echo "   sudo apt-get update && sudo apt-get install -y$MISSING_DEPS"
    fi
fi

echo ""
echo "=========================================="
echo "現在可以執行 python main.py 來啟動程式"
echo "=========================================="
