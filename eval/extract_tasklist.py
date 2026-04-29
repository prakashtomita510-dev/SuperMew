import pdfplumber
import sys

try:
    with pdfplumber.open(r'd:\agent_demo\SuperMew\docs\rag_eval_tasklist.pdf') as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text:
                print(f"--- PAGE {i+1} ---")
                print(text)
            else:
                print(f"--- PAGE {i+1} EMPTY OR UNEXTRACTABLE ---")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
