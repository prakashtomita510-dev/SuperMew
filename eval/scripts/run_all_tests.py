import subprocess
import time
import os

# All evaluation tasks in one sequential queue
TASKS = [
    # 1. Latency benchmark (P2-01) - High priority, smaller set
    {"config": "eval/configs/latency_sync.json", "dataset": "eval/datasets/custom/latency_benchmark_20.jsonl"},
    {"config": "eval/configs/latency_stream.json", "dataset": "eval/datasets/custom/latency_benchmark_20.jsonl"},
    
    # 2. Hybrid weight sweep (P1-01) - Core quality scan
    {"config": "eval/configs/hybrid_dense_only.json", "dataset": "eval/datasets/custom/custom_eval.jsonl"},
    {"config": "eval/configs/hybrid_dense_heavy.json", "dataset": "eval/datasets/custom/custom_eval.jsonl"},
    {"config": "eval/configs/hybrid_balanced.json", "dataset": "eval/datasets/custom/custom_eval.jsonl"},
    {"config": "eval/configs/hybrid_sparse_heavy.json", "dataset": "eval/datasets/custom/custom_eval.jsonl"},
    {"config": "eval/configs/hybrid_sparse_only.json", "dataset": "eval/datasets/custom/custom_eval.jsonl"},
]

python_exe = r".venv_311\Scripts\python.exe"

def run_all():
    for task in TASKS:
        config = task["config"]
        dataset = task["dataset"]
        if not os.path.exists(dataset):
            print(f"⚠️ Dataset {dataset} missing, skipping {config}")
            continue

        print(f"\n" + "="*60)
        print(f"🚀 STARTING TASK: {config}")
        print(f"="*60)
        
        try:
            subprocess.run([
                python_exe, "eval/scripts/run_rag_eval.py",
                "--config", config,
                "--dataset-path", dataset
            ], check=True)
            print(f"✅ TASK COMPLETED: {config}")
        except subprocess.CalledProcessError as e:
            print(f"❌ TASK FAILED: {config} with error: {e}")
            print("🛑 Stopping orchestration to prevent further API issues.")
            break
        
        print("☕ Cooling down for 10 seconds before next task...")
        time.sleep(10)

if __name__ == "__main__":
    run_all()
