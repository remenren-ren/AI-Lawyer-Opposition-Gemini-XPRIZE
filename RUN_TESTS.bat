@echo off
setlocal
cd /d "%~dp0"
set "NIDO_TEST_PY=python"
if exist "C:\Program Files\Python310\python.exe" set "NIDO_TEST_PY=C:\Program Files\Python310\python.exe"

"%NIDO_TEST_PY%" -m py_compile Nido_StrikeOver_Launcher_EN.py Nido_StrikeOver_Offline_EN.py Nido_StrikeOver_Online_EN.py Nido_Advanced_18D_Review_EN.py Nido_Advanced_Main_Opposition_2R_EN.py Nido_Advanced_Single_Point_2R_EN.py standard_report_contract.py offline_professional_report.py
if errorlevel 1 exit /b 1
"%NIDO_TEST_PY%" test_offline_professional_report.py
if errorlevel 1 exit /b 1
"%NIDO_TEST_PY%" test_offline_gui_report_bridge.py
if errorlevel 1 exit /b 1
"%NIDO_TEST_PY%" test_standard_report_system.py
if errorlevel 1 exit /b 1

pushd cloud_service
"%NIDO_TEST_PY%" -m py_compile app.py client_reception.py client_report_pdf.py professional_report.py pinch_payment_backend.py reception_billing.py
if errorlevel 1 exit /b 1
"%NIDO_TEST_PY%" test_deep88_flow.py
if errorlevel 1 exit /b 1
"%NIDO_TEST_PY%" test_funnel_visibility.py
if errorlevel 1 exit /b 1
"%NIDO_TEST_PY%" test_professional_outputs.py
if errorlevel 1 exit /b 1
popd

echo NIDO_JUDGE_BUILD_ALL_TESTS_OK
endlocal

