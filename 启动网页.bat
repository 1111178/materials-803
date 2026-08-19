@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   803 材料科学基础 知识库网页 一键启动
echo ============================================
echo.

set "PY=py"
py -3 --version >nul 2>nul
if not "%errorlevel%"=="0" set "PY=python"

echo [1/2] 安装依赖（首次较慢，约 1-2 分钟）...
%PY% -m pip install -r requirements.txt

echo.
echo [2/2] 启动网页...
echo 启动后浏览器会自动打开 http://localhost:8501
echo 关闭本窗口即停止网页。
echo.
%PY% -m streamlit run app.py

pause
