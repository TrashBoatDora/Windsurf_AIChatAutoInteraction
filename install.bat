@echo off
chcp 65001 >nul
echo ========================================
echo Hybrid UI Automation Script 安裝程式
echo ========================================
echo.

:: 檢查 Python 是否安裝
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 錯誤：未找到 Python，請先安裝 Python 3.8 或更新版本
    echo 下載地址：https://www.python.org/downloads/
    pause
    exit /b 1
)

echo ✓ Python 已安裝
echo.

:: 建立虛擬環境
echo 📦 建立 Python 虛擬環境...
python -m venv .venv
if errorlevel 1 (
    echo ❌ 建立虛擬環境失敗
    pause
    exit /b 1
)

echo ✓ 虛擬環境建立成功
echo.

:: 啟用虛擬環境並安裝套件
echo 📦 安裝必要的 Python 套件...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt

if errorlevel 1 (
    echo ❌ 安裝套件失敗，請檢查網路連線
    pause
    exit /b 1
)

echo.
echo ✅ 安裝完成！
echo.
echo 📁 建立必要的目錄...
if not exist "assets" mkdir assets
if not exist "logs" mkdir logs
if not exist "projects" mkdir projects
echo.

echo 🎯 下一步：
echo 1. 建立圖像模板檔案 (參考 assets\README.md)
echo 2. 將要處理的專案放入 projects\ 目錄
echo 3. 執行測試：.venv\Scripts\python.exe test_basic.py
echo 4. 開始自動化：.venv\Scripts\python.exe main.py
echo.
echo 或使用 run.bat 啟動圖形化選單
echo.
pause