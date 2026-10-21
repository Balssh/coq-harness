@echo off
set PYTHONHOME=C:\Users\georg\AppData\Local\Python\pythoncore-3.15-64
cd /d C:\Users\georg\coq-bridge
echo Starting bridge (connect mode)... > bridge_debug.log
bridgepython.exe -u -m bridge.server --window-title CavesOfQud --connect 172.24.136.20:9091 --log-region 1440 0 480 1000 >> bridge_debug.log 2>&1
