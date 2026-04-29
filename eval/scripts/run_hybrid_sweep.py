import subprocess
import time
import os

configs = [
    "eval/configs/hybrid_dense_only.json",
    "eval/configs/hybrid_dense_heavy.json",
    "eval/configs/hybrid_balanced.json",
    "eval/configs/hybrid_sparse_heavy.json",
    "eval/configs/hybrid_sparse_only.json"
]

dataset = "eval/datasets/custom/custom_eval.jsonl"
python_exe = r".venv_311\Scripts\python.exe"

def run_sweep():
    for config in configs:
        print(f"Starting eval for {config}...")
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
    run_sweep()
