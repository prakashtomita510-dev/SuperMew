import json
from pathlib import Path

def diagnose_accuracy():
    eval_dir = Path("d:/agent_demo/SuperMew/eval")
    record_path = eval_dir / "outputs/rewrite/dynamic_rewrite/records.jsonl"
    report_path = eval_dir / "outputs/reports/answer_quality_failure_analysis.md"

    samples = []
    with open(record_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            record = json.loads(line)
            acc = record.get("answer_accuracy")
            if acc is None: acc = 0
            groundedness = record.get("groundedness_score")
            if groundedness is None: groundedness = 0
            
            if acc < 0.2 and groundedness > 0.8:
                samples.append(record)

    # Sort by accuracy (lowest first)
    def get_acc(x):
        a = x.get("answer_accuracy")
        return a if a is not None else 0
    samples.sort(key=get_acc)
    
    # Take top 20
    diagnosis_samples = samples[:20]

    report_md = "# Answer Quality Failure Analysis\n\n"
    report_md += f"Analyzing {len(diagnosis_samples)} samples with low accuracy (<0.2) but high groundedness (>0.8).\n\n"
    
    for i, s in enumerate(diagnosis_samples):
        report_md += f"### Sample {i+1}: {s.get('question_id')}\n"
        report_md += f"- **Question**: {s.get('question')}\n"
        report_md += f"- **Accuracy**: {s.get('answer_accuracy')}\n"
        report_md += f"- **Groundedness**: {s.get('groundedness_score')}\n"
        report_md += f"- **Gold Answer**: {s.get('gold_answer')}\n"
        report_md += f"- **Pred Answer**: {s.get('pred_answer')}\n"
        
        # Add a placeholder for manual categorization
        report_md += f"- **Diagnosis Category**: [TODO]\n"
        report_md += f"- **Notes**: \n\n"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    print(f"Diagnosis report generated at {report_path}")

if __name__ == "__main__":
    diagnose_accuracy()
