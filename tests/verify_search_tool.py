import sys
import os
from dotenv import load_dotenv

# Add backend to sys.path for importing tools
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from tools import internet_crawler_search

def test_internet_search():
    print("Testing internet_crawler_search tool...")
    query = "What is the capital of France?"
    result = internet_crawler_search.invoke({"query": query})
    
    if "Paris" in result:
        print("✅ SUCCESS: Found 'Paris' in search results.")
    else:
        print(f"❌ FAILURE: Did not find expected result. Result: {result}")

    print("\nTesting with a real-time query...")
    query_realtime = "Who won the Best Picture at the 2024 Oscars?"
    result_rt = internet_crawler_search.invoke({"query": query_realtime})
    
    if "Oppenheimer" in result_rt:
        print("✅ SUCCESS: Found 'Oppenheimer' in real-time results.")
    else:
        print(f"❌ FAILURE: Did not find expected result. Result: {result_rt[:200]}...")

if __name__ == "__main__":
    test_internet_search()
