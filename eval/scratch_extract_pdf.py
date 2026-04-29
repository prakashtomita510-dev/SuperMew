import pdfplumber
import sys

pdf = pdfplumber.open(r'd:\agent_demo\SuperMew\docs\rag_eval_tasklist.pdf')
for i, page in enumerate(pdf.pages):
    text = page.extract_text()
    if text:
        print(f"=== PAGE {i+1} ===")
        print(text)
