import subprocess
import time
import os
from pathlib import Path

configs = [
    "eval/configs/latency_sync.json",
    "eval/configs/latency_stream.json"
]

dataset = "eval/datasets/custom/latency_benchmark_20.jsonl"
python_exe = r".venv_311\Scripts\python.exe"

def run_benchmark():
    for config in configs:
        print(f"Starting latency benchmark for {config}...")
        start_time = time.time()
        try:
            subprocess.run([
                python_exe, "eval/scripts/run_rag_eval.py",
                "--config", config,
                "--dataset-path", dataset
            ], check=True)
            elapsed = time.time() - start_time
            print(f"Finished {config} in {elapsed:.2f}s")
        except subprocess.CalledProcessError as e:
            print(f"Error running {config}: {e}")

if __name__ == "__main__":
    # Ensure dataset exists
    if not os.path.exists(dataset):
        print(f"Dataset {dataset} missing. Please create it first.")
    else:
        run_benchmark()
