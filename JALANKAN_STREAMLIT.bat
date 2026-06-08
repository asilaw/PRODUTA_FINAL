@echo off
REM Jalankan Streamlit dengan venv311 (Python 3.11 + statsmodels)
IF EXIST venv311\Scripts\activate.bat (
    call venv311\Scripts\activate.bat
    streamlit run app.py
) ELSE (
    echo [ERROR] venv311 belum dibuat. Jalankan SETUP_PYTHON311.bat dulu!
    pause
)
