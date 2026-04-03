import sys
import os
from dotenv import load_dotenv

# Add backend to sys.path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from rag_pipeline import run_rag_graph

def test_router():
    test_cases = [
        ("你好！", "chitchat"),
        ("Transformer 模型的设计理念是什么？", "rag"),
        ("北京今天的天气怎么样？", "weather")
    ]
    
    print("=== Phase 6: Router & Multi-Query Test ===")
    for question, expected in test_cases:
        print(f"\nProcessing: '{question}'")
        res = run_rag_graph(question)
        intent = res.get("intent")
        queries = res.get("queries", [])
        answer = res.get("answer", "")
        
        print(f"Detected Intent: {intent}")
        if intent == "rag":
            print(f"Generated Queries: {queries}")
        if answer:
            print(f"Answer Sample: {answer[:100]}...")
            
if __name__ == "__main__":
    test_router()
