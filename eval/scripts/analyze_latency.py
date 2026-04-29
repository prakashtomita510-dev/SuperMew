import json
import os
from collections import defaultdict

records_path = r"d:\agent_demo\SuperMew\eval\outputs\chunking\auto_merge\records.jsonl"
report_path = r"d:\agent_demo\SuperMew\eval\outputs\reports\stage_latency_breakdown.md"

def analyze_latency():
    stage_totals = defaultdict(float)
    counts = defaultdict(int)
    total_latency = 0.0
    total_samples = 0
    
    with open(records_path, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            trace = data.get("rag_trace", {})
            timings = trace.get("stage_timings_ms", {})
            
            gen_latency = data.get("generation_latency_ms", 0.0)
            total_latency += gen_latency
            total_samples += 1
            
            for stage, ms in timings.items():
                stage_totals[stage] += ms
                counts[stage] += 1

    if total_samples == 0:
        print("No samples found.")
        return

    avg_total = total_latency / total_samples
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# RAG End-to-End Latency Breakdown\n\n")
        f.write(f"Analyzed {total_samples} samples from `{os.path.basename(records_path)}`.\n")
        f.write(f"**Average End-to-End Latency**: {avg_total/1000:.2f}s\n\n")
        
        f.write("| Stage | Avg Latency (s) | % of Total |\n")
        f.write("| :--- | :--- | :--- |\n")
        
        # Sort stages by latency descending
        sorted_stages = sorted(stage_totals.items(), key=lambda x: x[1], reverse=True)
        
        for stage, total_ms in sorted_stages:
            avg_s = (total_ms / counts[stage]) / 1000
            pct = (total_ms / total_latency) * 100
            f.write(f"| {stage} | {avg_s:.2f}s | {pct:.1f}% |\n")
            
        f.write("\n\n## Analysis & Bottlenecks\n\n")
        
        # Heuristics for bottlenecks
        if "retrieve_ms" in stage_totals:
            retrieve_pct = (stage_totals["retrieve_ms"] / total_latency) * 100
            if retrieve_pct > 50:
                f.write("- **Retrieval is the primary bottleneck** (>50%). Consider optimizing embedding generation or vector search.\n")
        
        if "generate_ms" in stage_totals:
            gen_pct = (stage_totals["generate_ms"] / total_latency) * 100
            if gen_pct > 40:
                f.write("- **LLM Generation time is significant**. Consider streaming or a faster model.\n")
        
        if "rewrite_ms" in stage_totals:
            f.write("- **Rewrite Logic**: This includes grading and query expansion. If this is high, we should investigate if we can skip grading for simple queries.\n")

if __name__ == "__main__":
    analyze_latency()
