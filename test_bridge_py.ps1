$env:PYTHONHOME = "C:\Users\georg\AppData\Local\Python\pythoncore-3.15-64"
cd "C:\Users\georg\coq-bridge"
.\bridgepython.exe -c "import numpy, PIL, win32gui, windows_capture; print('all imports OK')"
