import sys
import os
import asyncio
from dotenv import load_dotenv

# Add backend to sys.path
current_dir = os.getcwd()
backend_dir = os.path.join(current_dir, 'backend')
sys.path.append(backend_dir)

# Ensure DATABASE_URL points to the correct db file in backend/
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(backend_dir, 'supermew.db')}"

from tools import search_knowledge_base

def test_self_rag_tool():
    print("Testing Self-RAG (Self-Correction) Tool...")
    # This query should trigger retrieval and then generation + grading
    query = "What information is in the uploaded knowledge base?"
    
    print(f"Query: {query}")
    try:
        # Call the tool directly
        result = search_knowledge_base.invoke({"query": query})
        
        print("\nTool Result Output:")
        print("-" * 20)
        print(result)
        print("-" * 20)
        
        if "Knowledge Base Answer:" in result and len(result) > 50:
            print("✅ SUCCESS: Tool returned a generated answer instead of raw chunks.")
        else:
            print("❌ FAILURE: Tool did not return expected format or content.")
            
    except Exception as e:
        print(f"❌ ERROR while calling tool: {e}")

if __name__ == "__main__":
    test_self_rag_tool()
