
import sys

packages = ['pandas', 'selenium', 'webdriver_manager']
missing = []

for p in packages:
    try:
        __import__(p)
        print(f"{p}: OK")
    except ImportError:
        print(f"{p}: MISSING")
        missing.append(p)

if missing:
    print(f"Missing packages: {', '.join(missing)}")
    sys.exit(1)
print("All packages installed.")
