@echo off
echo ============================================================
echo  PRODUTA - Setup Environment Python 3.11
echo  Jalankan file ini SATU KALI untuk setup yang benar
echo ============================================================
echo.

REM Cek apakah py launcher ada (biasanya ada di Windows)
py -3.11 --version 2>nul
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python 3.11 tidak ditemukan!
    echo Download dari: https://www.python.org/downloads/release/python-3119/
    echo Pastikan centang "Add to PATH" saat install
    pause
    exit /b 1
)

echo [1/3] Membuat virtual environment baru dengan Python 3.11...
IF EXIST venv311 (
    echo   - Folder venv311 sudah ada, skip pembuatan
) ELSE (
    py -3.11 -m venv venv311
    echo   - venv311 berhasil dibuat
)

echo.
echo [2/3] Install semua package yang dibutuhkan...
call venv311\Scripts\activate.bat
pip install --upgrade pip
pip install streamlit>=1.28.0 pandas>=2.0.0 numpy>=1.24.0 numpy_financial plotly scipy scikit-fuzzy openpyxl xlsxwriter simpy statsmodels

echo.
echo [3/3] Install Prophet (ini butuh waktu ~5 menit, sabar ya)...
pip install prophet

echo.
echo ============================================================
echo  Setup selesai! Cara jalankan Streamlit:
echo.
echo  venv311\Scripts\activate
echo  streamlit run app.py
echo ============================================================
pause
