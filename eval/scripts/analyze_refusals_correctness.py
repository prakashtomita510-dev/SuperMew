import json
import os

records_path = r"d:\agent_demo\SuperMew\eval\outputs\chunking\auto_merge\records.jsonl"
report_path = r"d:\agent_demo\SuperMew\eval\outputs\reports\refusal_correctness.md"

refusal_keywords = ["抱歉", "无法回答", "没有提及", "未提及", "不包含", "没有找到", "does not mention", "cannot answer", "sorry"]

def analyze_refusals():
    total_unanswerable = 0
    correct_refusals = 0
    false_refusals = 0 # unanswerable=false but model refused
    total_answerable = 0
    
    details = []

    if not os.path.exists(records_path):
        print("Records not found.")
        return

    with open(records_path, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            qid = data.get("question_id")
            is_unanswerable = data.get("is_unanswerable", False)
            pred = data.get("pred_answer", "").lower()
            
            is_refusal = any(kw in pred for kw in refusal_keywords)
            
            if is_unanswerable:
                total_unanswerable += 1
                if is_refusal:
                    correct_refusals += 1
                    status = "✅ Correct Refusal"
                else:
                    status = "❌ Hallucinated Answer"
            else:
                total_answerable += 1
                if is_refusal:
                    false_refusals += 1
                    status = "❌ False Refusal"
                else:
                    status = "✅ Attempted Answer"
            
            if is_refusal or is_unanswerable:
                details.append({
                    "id": qid,
                    "is_unanswerable": is_unanswerable,
                    "is_refusal": is_refusal,
                    "status": status,
                    "pred": pred[:100] + "..."
                })

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Refusal Correctness Analysis (P1-04)\n\n")
        
        f.write(f"## Summary Metrics\n")
        f.write(f"- **True Unanswerable Samples**: {total_unanswerable}\n")
        if total_unanswerable > 0:
            f.write(f"  - Correct Refusals: {correct_refusals} ({correct_refusals/total_unanswerable*100:.1f}%)\n")
            f.write(f"  - Hallucinations (Answered when should refuse): {total_unanswerable - correct_refusals}\n")
        
        f.write(f"- **True Answerable Samples**: {total_answerable}\n")
        if total_answerable > 0:
            f.write(f"  - False Refusals (Refused when should answer): {false_refusals} ({false_refusals/total_answerable*100:.1f}%)\n")
            f.write(f"  - Answer Attempts: {total_answerable - false_refusals}\n\n")
        
        f.write("## Detailed Refusal Status\n\n")
        f.write("| ID | Unanswerable (Gold) | Refusal (Pred) | Status | Pred Snippet |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        for d in details:
            f.write(f"| {d['id']} | {d['is_unanswerable']} | {d['is_refusal']} | {d['status']} | {d['pred']} |\n")

if __name__ == "__main__":
    analyze_refusals()
