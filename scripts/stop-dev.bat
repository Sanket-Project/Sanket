@echo off
REM Stops the SANKET dev stack started by Start_SANKET.bat / start-dev.bat.
REM The services die with the launcher (they share its Windows job), so ending
REM the launcher's process tree stops all of them. Docker's postgres/redis stay up.

echo Stopping SANKET dev services...
powershell -NoProfile -Command "$found = @(Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -like '*-m scripts.dev_stack*' }); foreach ($p in $found) { taskkill /PID $p.ProcessId /T /F 2>$null | Out-Null }; if ($found.Count) { 'Stopped.' } else { 'The SANKET dev stack is not running.' }"
