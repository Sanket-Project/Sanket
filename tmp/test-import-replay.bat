@echo off
call "%~dp0run-test.bat" tests/test_sales_import_replay.py -q -p no:cacheprovider
