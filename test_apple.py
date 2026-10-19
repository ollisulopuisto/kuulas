import sys
import subprocess
import time

def run():
    start = time.time()
    if sys.platform != "darwin":
        return
    subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True, text=True, timeout=2, check=False)
    print(f"Time taken: {time.time() - start:.2f}s")
run()
