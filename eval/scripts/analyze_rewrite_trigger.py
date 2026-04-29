import json
import os
from pathlib import Path

def analyze_rewrite_trigger():
    eval_dir = Path("d:/agent_demo/SuperMew/eval")
    custom_eval_path = eval_dir / "datasets/custom/custom_eval.jsonl"
    rewrite_output_dir = eval_dir / "outputs/rewrite"
    report_path = eval_dir / "outputs/reports/rewrite_by_question_type.md"

    # 1. Load ground truth
    ground_truth = {}
    with open(custom_eval_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            ground_truth[item["id"]] = {
                "question_type": item["question_type"],
                "needs_rewrite": item["needs_rewrite"]
            }

    variants = ["no_rewrite", "always_step_back", "always_hyde", "dynamic_rewrite"]
    data = []

    for variant in variants:
        record_path = rewrite_output_dir / variant / "records.jsonl"
        if not record_path.exists():
            print(f"Warning: {record_path} not found.")
            continue

        with open(record_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                qid = record.get("question_id") or record.get("id")
                if qid not in ground_truth:
                    continue
                
                gt = ground_truth[qid]
                rag_trace = record.get("rag_trace", {})
                
                triggered = rag_trace.get("retrieval_stage") == "expanded"
                
                accuracy = record.get("answer_accuracy")
                if accuracy is None: accuracy = 0
                latency = record.get("generation_latency_ms")
                if latency is None: latency = 0
                
                data.append({
                    "variant": variant,
                    "id": qid,
                    "question_type": gt["question_type"],
                    "needs_rewrite": gt["needs_rewrite"],
                    "triggered": triggered,
                    "accuracy": accuracy,
                    "latency_ms": latency
                })

    if not data:
        print("No data found to analyze.")
        return

    # Calculate statistics manually
    report_md = "# Rewrite Trigger Analysis by Question Type\n\n"
    report_md += f"Analysis based on {len(ground_truth)} reviewed custom samples.\n\n"

    # Group by variant and then by question_type
    stats = {}
    for item in data:
        v = item["variant"]
        qt = item["question_type"]
        if v not in stats: stats[v] = {}
        if qt not in stats[v]: 
            stats[v][qt] = {
                "count": 0, "triggered": 0, "acc_sum": 0, "lat_sum": 0,
                "tp": 0, "fp": 0, "tn": 0, "fn": 0
            }
        
        s = stats[v][qt]
        s["count"] += 1
        if item["triggered"]: s["triggered"] += 1
        s["acc_sum"] += item["accuracy"]
        s["lat_sum"] += item["latency_ms"]
        
        if item["triggered"] and item["needs_rewrite"]: s["tp"] += 1
        elif item["triggered"] and not item["needs_rewrite"]: s["fp"] += 1
        elif not item["triggered"] and not item["needs_rewrite"]: s["tn"] += 1
        elif not item["triggered"] and item["needs_rewrite"]: s["fn"] += 1

    for variant in variants:
        if variant not in stats: continue
        v_stats = stats[variant]
        
        report_md += f"## Variant: {variant}\n\n"
        
        total_count = sum(s["count"] for s in v_stats.values())
        total_triggered = sum(s["triggered"] for s in v_stats.values())
        total_acc = sum(s["acc_sum"] for s in v_stats.values())
        total_lat = sum(s["lat_sum"] for s in v_stats.values())
        
        report_md += f"- **Total Samples**: {total_count}\n"
        report_md += f"- **Overall Trigger Rate**: {total_triggered/total_count:.2%} ({total_triggered}/{total_count})\n"
        report_md += f"- **Mean Accuracy**: {total_acc/total_count:.4f}\n"
        report_md += f"- **Mean Latency**: {total_lat/total_count/1000:.2f}s\n\n"

        report_md += "| Question Type | Count | Triggered | TP | FP | FN | Acc | Latency |\n"
        report_md += "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        
        sorted_types = sorted(v_stats.keys())
        for qt in sorted_types:
            s = v_stats[qt]
            report_md += f"| {qt} | {s['count']} | {s['triggered']} | {s['tp']} | {s['fp']} | {s['fn']} | {s['acc_sum']/s['count']:.4f} | {s['lat_sum']/s['count']/1000:.2f}s |\n"
        report_md += "\n"

    # Delta Analysis
    if "no_rewrite" in stats:
        report_md += "## Delta Analysis (Relative to no_rewrite)\n\n"
        baseline = stats["no_rewrite"]
        
        for variant in variants:
            if variant == "no_rewrite" or variant not in stats: continue
            report_md += f"### {variant} vs no_rewrite\n\n"
            report_md += "| Question Type | Acc Delta | Latency Delta | Trigger Correctness |\n"
            report_md += "| --- | --- | --- | --- |\n"
            
            v_stats = stats[variant]
            sorted_types = sorted(v_stats.keys())
            for qt in sorted_types:
                if qt not in baseline: continue
                s = v_stats[qt]
                b = baseline[qt]
                
                acc_delta = (s["acc_sum"]/s["count"]) - (b["acc_sum"]/b["count"])
                lat_delta = (s["lat_sum"]/s["count"] - b["lat_sum"]/b["count"]) / 1000
                
                precision = s["tp"] / (s["tp"] + s["fp"]) if (s["tp"] + s["fp"]) > 0 else 0
                recall = s["tp"] / (s["tp"] + s["fn"]) if (s["tp"] + s["fn"]) > 0 else 0
                
                report_md += f"| {qt} | {acc_delta:+.4f} | {lat_delta:+.2f}s | P={precision:.2f}, R={recall:.2f} |\n"
            report_md += "\n"

    # Conclusion
    report_md += "## Findings\n\n"
    if "dynamic_rewrite" in stats:
        d = stats["dynamic_rewrite"]
        total_tp = sum(s["tp"] for s in d.values())
        total_fp = sum(s["fp"] for s in d.values())
        total_fn = sum(s["fn"] for s in d.values())
        
        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        
        report_md += f"- **Dynamic Rewrite Precision**: {precision:.2%}\n"
        report_md += f"- **Dynamic Rewrite Recall**: {recall:.2%}\n"
        report_md += f"- **False Positives**: {total_fp} (Triggered but labeled as not needing rewrite)\n"
        report_md += f"- **False Negatives**: {total_fn} (Not triggered but labeled as needing rewrite)\n"

    os.makedirs(report_path.parent, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)
    
    print(f"Report generated at {report_path}")

if __name__ == "__main__":
    analyze_rewrite_trigger()
