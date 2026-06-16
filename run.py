import os
import sys
import subprocess
import webbrowser
import time
import signal

def main():
    print("==================================================================")
    print("         E-PATROL AI // Behavioral Reasoning Engine               ")
    print("==================================================================")
    
    # 1. Detect environment
    root_dir = os.path.dirname(os.path.abspath(__file__))
    venv_dir = os.path.join(root_dir, "venv")
    
    python_bin = sys.executable
    if os.path.exists(venv_dir):
        if sys.platform == "win32":
            python_bin = os.path.join(venv_dir, "Scripts", "python.exe")
        else:
            python_bin = os.path.join(venv_dir, "bin", "python")
        print(f"[NOMINAL] Virtual environment detected: {venv_dir}")
    else:
        print("[WARNING] Virtual environment not found. Using system python.")
        print("          It is highly recommended to run: python -m venv venv && .\\venv\\Scripts\\pip install -r backend/requirements.txt")
    
    # 2. Check backend directory
    backend_dir = os.path.join(root_dir, "backend")
    if not os.path.exists(backend_dir):
        print(f"[FATAL] Backend directory not found at {backend_dir}!")
        sys.exit(1)
        
    # 3. Launch FastAPI server
    # Uvicorn needs to be run inside the backend folder to resolve relative static paths
    print("[SYSTEM] Starting E-Patrol API Gateway on port 8000...")
    cmd = [python_bin, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"]
    
    process = None
    try:
        process = subprocess.Popen(
            cmd,
            cwd=backend_dir,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        
        # 4. Wait for server to bind and open browser
        time.sleep(2.0)
        dashboard_url = "http://127.0.0.1:8000/dashboard/"
        print(f"[SYSTEM] Opening E-Patrol Control Center: {dashboard_url}")
        webbrowser.open(dashboard_url)
        
        # 5. Monitor process
        while True:
            ret = process.poll()
            if ret is not None:
                print(f"[FATAL] Backend server exited with code {ret}")
                break
            time.sleep(1.0)
            
    except KeyboardInterrupt:
        print("\n[SYSTEM] Intercepted shutdown signal. Stopping E-Patrol server...")
    except Exception as e:
        print(f"[FATAL] Launch failed: {e}")
    finally:
        if process:
            # Clean shutdown on Windows
            if sys.platform == "win32":
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(process.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                process.terminate()
            print("[SYSTEM] E-Patrol services stopped successfully.")

if __name__ == "__main__":
    main()
