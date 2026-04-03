import os
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent / "backend"))

if __name__ == "__main__":
    try:
        from backend.app import app
        import uvicorn
        print("SuperMew Backend Starting...")
        uvicorn.run(app, host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", 8000)))
    except ImportError as e:
        print(f"[Error] Missing dependencies: {e}")
        print("Please use: .\\.venv_311\\Scripts\\python main.py")
        sys.exit(1)