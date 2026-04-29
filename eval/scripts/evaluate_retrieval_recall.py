import json
from pathlib import Path

def evaluate_retrieval_recall():
    eval_dir = Path("d:/agent_demo/SuperMew/eval")
    custom_eval_path = eval_dir / "datasets/custom/custom_eval.jsonl"
    rewrite_output_dir = eval_dir / "outputs/rewrite"
    report_path = eval_dir / "outputs/reports/retrieval_recall_analysis.md"

    # 1. Load ground truth
    ground_truth = {}
    with open(custom_eval_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            item = json.loads(line)
            if item.get("is_unanswerable"): continue
            ground_truth[item["id"]] = item.get("gold_spans", [])

    variants = ["no_rewrite", "always_step_back", "always_hyde", "dynamic_rewrite"]
    
    report_md = "# Retrieval Recall Analysis\n\n"
    report_md += f"Analysis based on {len(ground_truth)} answerable custom samples.\n\n"
    report_md += "| Variant | Recall@1 | Recall@3 | Recall@5 |\n"
    report_md += "| --- | --- | --- | --- |\n"

    for variant in variants:
        record_path = rewrite_output_dir / variant / "records.jsonl"
        if not record_path.exists():
            continue

        hits_at_k = {1: 0, 3: 0, 5: 0}
        total_samples = 0

        with open(record_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                record = json.loads(line)
                qid = record.get("question_id") or record.get("id")
                if qid not in ground_truth: continue
                
                total_samples += 1
                gold_spans = ground_truth[qid]
                
                # Get retrieved chunks
                rag_trace = record.get("rag_trace", {})
                retrieved_chunks = rag_trace.get("retrieved_chunks") or rag_trace.get("retrieval_stage_results") or []
                
                retrieved_texts = []
                for res in retrieved_chunks:
                    text = res.get("text") or res.get("content") or ""
                    retrieved_texts.append(text)

                def normalize(t):
                    return "".join(t.lower().split())

                # Check hits
                for k in [1, 3, 5]:
                    top_k_chunks = retrieved_texts[:k]
                    is_hit = False
                    for gold in gold_spans:
                        gold_text = gold.get("span_text", "").strip()
                        if not gold_text: continue
                        
                        norm_gold = normalize(gold_text)
                        
                        # Check if gold_text is in any of the top_k_chunks
                        for chunk in top_k_chunks:
                            norm_chunk = normalize(chunk)
                            if norm_gold in norm_chunk or norm_chunk in norm_gold:
                                is_hit = True
                                break
                        if is_hit: break
                    
                    if is_hit:
                        hits_at_k[k] += 1

        if total_samples > 0:
            r1 = hits_at_k[1] / total_samples
            r3 = hits_at_k[3] / total_samples
            r5 = hits_at_k[5] / total_samples
            report_md += f"| {variant} | {r1:.2%} | {r3:.2%} | {r5:.2%} |\n"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)
    
    print(f"Recall report generated at {report_path}")

if __name__ == "__main__":
    evaluate_retrieval_recall()
