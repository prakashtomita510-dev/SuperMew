import json
import os

records_path = r"d:\agent_demo\SuperMew\eval\outputs\chunking\auto_merge\records.jsonl"
output_report = r"d:\agent_demo\SuperMew\eval\outputs\reports\refusal_retrieval_analysis.md"

def analyze():
    refusals = []
    with open(records_path, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            pred = data.get("pred_answer", "")
            accuracy = data.get("answer_accuracy", 0.0)
            
            # Keywords indicating refusal or missing content
            refusal_keywords = ["不包含", "没有提到", "无法找到", "not contain", "does not mention", "no information"]
            is_refusal = any(kw in pred for kw in refusal_keywords)
            
            acc_val = accuracy if accuracy is not None else 0.0
            if is_refusal or acc_val < 0.05:
                refusals.append(data)

    with open(output_report, "w", encoding="utf-8") as f:
        f.write("# Refusal and Low Accuracy Retrieval Analysis\n\n")
        f.write(f"Found {len(refusals)} samples with potential retrieval or refusal issues.\n\n")
        
        for item in refusals:
            qid = item.get("question_id")
            query = item.get("query")
            pred = item.get("pred_answer")
            gold = item.get("gold_answer")
            accuracy = item.get("answer_accuracy")
            trace = item.get("rag_trace", {})
            retrieved = trace.get("retrieved_chunks", [])
            
            f.write(f"## Sample {qid}\n")
            f.write(f"- **Query**: {query}\n")
            f.write(f"- **Accuracy**: {accuracy}\n")
            f.write(f"- **Prediction**: {pred}\n")
            f.write(f"- **Gold (Snippet)**: {gold[:200]}...\n")
            f.write(f"- **Retrieved Pages**: {list(set([c.get('page_number') for c in retrieved]))}\n")
            f.write(f"- **Retrieved Chunks**:\n")
            for c in retrieved:
                f.write(f"  - [Page {c.get('page_number')}] {c.get('chunk_id')} (Score: {c.get('score'):.4f})\n")
            f.write("\n---\n\n")

if __name__ == "__main__":
    analyze()
