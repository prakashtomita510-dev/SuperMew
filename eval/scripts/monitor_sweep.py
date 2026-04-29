import os
import time
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.live import Live
from pathlib import Path

# Config
OUTPUT_DIR = Path("eval/outputs")
REFRESH_INTERVAL = 5 # seconds

console = Console()

def get_metrics():
    all_metrics = []
    if not OUTPUT_DIR.exists():
        return []
    
    for csv_file in OUTPUT_DIR.glob("live_results_*.csv"):
        variant = csv_file.stem.replace("live_results_", "")
        try:
            df = pd.read_csv(csv_file, on_bad_lines='skip')
            if df.empty:
                continue
            
            # Filter out header repeats if any
            df = df[df['question_id'] != 'question_id']
            count = len(df)
            
            def safe_mean(col_name):
                if col_name in df:
                    vals = pd.to_numeric(df[col_name], errors='coerce')
                    return vals.mean() if not vals.isnull().all() else 0
                return 0

            avg_latency = safe_mean('latency_ms') / 1000
            avg_ttft = safe_mean('ttft_ms') / 1000
            acc_f1 = safe_mean('answer_accuracy_f1')
            acc_sem = safe_mean('answer_accuracy_semantic')
            cit_prec = safe_mean('citation_precision')
            cit_rec = safe_mean('citation_recall')
            groundedness = safe_mean('groundedness_score')
            refusal_correctness = safe_mean('is_refusal_correct')
            
            all_metrics.append({
                "Variant": variant,
                "Samples": count,
                "Lat(s)": f"{avg_latency:.2f}",
                "TTFT(s)": f"{avg_ttft:.2f}" if avg_ttft > 0 else "-",
                "F1": f"{acc_f1:.4f}",
                "Sem": f"{acc_sem:.4f}",
                "CitPrec": f"{cit_prec:.4f}",
                "CitRec": f"{cit_rec:.4f}",
                "Gnd": f"{groundedness:.2f}" if groundedness > 0 else "-",
                "RefCor": f"{refusal_correctness:.2f}"
            })
        except Exception:
            pass
            
    return sorted(all_metrics, key=lambda x: x["Variant"])

def generate_table():
    metrics = get_metrics()
    table = Table(title=f"[bold blue]SuperMew RAG Eval Sweep Monitor[/bold blue] (Auto-refresh {REFRESH_INTERVAL}s)", title_justify="left")
    
    table.add_column("Variant", style="cyan", no_wrap=True)
    table.add_column("Samples", justify="right")
    table.add_column("Lat(s)", justify="right")
    table.add_column("TTFT(s)", justify="right")
    table.add_column("F1", justify="right", style="green")
    table.add_column("Sem", justify="right", style="green")
    table.add_column("CitPrec", justify="right", style="magenta")
    table.add_column("CitRec", justify="right", style="magenta")
    table.add_column("Gnd", justify="right", style="yellow")
    table.add_column("RefCor", justify="right", style="cyan")
    
    if not metrics:
        table.add_row("No data yet...", "-", "-", "-", "-", "-", "-", "-", "-", "-")
    else:
        for m in metrics:
            table.add_row(
                m["Variant"],
                str(m["Samples"]),
                m["Lat(s)"],
                m["TTFT(s)"],
                m["F1"],
                m["Sem"],
                m["CitPrec"],
                m["CitRec"],
                m["Gnd"],
                m["RefCor"]
            )
    
    return table

if __name__ == "__main__":
    console.clear()
    with Live(generate_table(), refresh_per_second=1, screen=True) as live:
        while True:
            live.update(generate_table())
            time.sleep(REFRESH_INTERVAL)
