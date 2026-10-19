import subprocess
import time
start = time.time()
subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True, text=True, timeout=2, check=False)
print(time.time() - start)
