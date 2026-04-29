import json
import re
import os

records_path = r"d:\agent_demo\SuperMew\eval\outputs\chunking\auto_merge\records.jsonl"
report_path = r"d:\agent_demo\SuperMew\eval\outputs\reports\citation_coverage.md"

def analyze_citations():
    total_citations = 0
    valid_citations = 0
    samples_with_citations = 0
    total_samples = 0
    
    details = []

    if not os.path.exists(records_path):
        print("Records not found.")
        return

    with open(records_path, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            qid = data.get("question_id")
            pred = data.get("pred_answer", "")
            trace = data.get("rag_trace", {})
            retrieved = trace.get("retrieved_chunks", [])
            gold_spans = data.get("gold_spans", [])
            
            total_samples += 1
            
            # Find all [N]
            matches = re.findall(r"\[(\d+)\]", pred)
            if matches:
                samples_with_citations += 1
                sample_valid = 0
                sample_total = 0
                
                for m in matches:
                    idx = int(m) - 1 # 1-based to 0-based
                    sample_total += 1
                    total_citations += 1
                    
                    if 0 <= idx < len(retrieved):
                        chunk = retrieved[idx]
                        c_page = chunk.get("page_number")
                        c_file = os.path.basename(chunk.get("filename") or "")
                        
                        # Check if matches any gold span
                        is_valid = False
                        for span in gold_spans:
                            g_page = span.get("page_number")
                            g_file = os.path.basename(span.get("doc_id") or "")
                            
                            if c_page == g_page and (not g_file or g_file in c_file or c_file in g_file):
                                is_valid = True
                                break
                        
                        if is_valid:
                            valid_citations += 1
                            sample_valid += 1
                
                details.append({
                    "id": qid,
                    "total": sample_total,
                    "valid": sample_valid,
                    "score": sample_valid / sample_total if sample_total > 0 else 0
                })

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Citation Coverage Analysis (P1-05)\n\n")
        f.write(f"- **Samples with Citations**: {samples_with_citations} / {total_samples}\n")
        f.write(f"- **Total Citation Links**: {total_citations}\n")
        if total_citations > 0:
            f.write(f"- **Valid Citations (Match Gold Page/File)**: {valid_citations} ({valid_citations/total_citations*100:.1f}%)\n\n")
        
        f.write("## Detailed Citation Accuracy\n\n")
        f.write("| ID | Total Links | Valid Links | Accuracy |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        for d in details:
            f.write(f"| {d['id']} | {d['total']} | {d['valid']} | {d['score']:.1f} |\n")

if __name__ == "__main__":
    analyze_citations()
