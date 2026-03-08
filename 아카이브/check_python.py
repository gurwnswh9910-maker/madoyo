
import sys
import os
import shutil

try:
    with open('python_info.txt', 'w', encoding='utf-8') as f:
        f.write(f"Executable: {sys.executable}\n")
        f.write(f"Version: {sys.version}\n")
        f.write(f"Cwd: {os.getcwd()}\n")
        pip_path = shutil.which("pip")
        f.write(f"Pip path: {pip_path}\n")
        try:
            import pip
            f.write(f"Pip module: {pip.__file__}\n")
        except ImportError:
            f.write("Pip module: missing\n")
except Exception as e:
    print(e)
