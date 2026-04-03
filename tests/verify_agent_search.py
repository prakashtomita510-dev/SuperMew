import sys
import os
import asyncio
from dotenv import load_dotenv

# Add backend to sys.path for importing agent
current_dir = os.getcwd()
backend_dir = os.path.join(current_dir, 'backend')
sys.path.append(backend_dir)

# Ensure DATABASE_URL points to the correct db file in backend/
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(backend_dir, 'supermew.db')}"

from agent import chat_with_agent, chat_with_agent_stream

async def test_agent_internet_search():
    print("Testing Agent Integration with Internet Search...")
    user_query = "What is the top headline on CNN right now? (April 2026 test)"
    
    # Test streaming to see the 'internet_crawler_search' tool call and its output
    print(f"User Query: {user_query}")
    
    found_search_step = False
    full_response = ""
    
    async for chunk in chat_with_agent_stream(user_query, "test_user", "test_session"):
        # chunk is a JSON string from StreamingResponse
        import json
        if chunk.startswith("data: "):
            data_str = chunk[6:].strip()
            if data_str == "[DONE]": continue
            try:
                data = json.loads(data_str)
                if data.get("type") == "rag_step":
                    step = data.get("step", {})
                    print(f"Step: {step.get('icon')} {step.get('label')}")
                    if "联网搜索" in step.get("label"):
                        found_search_step = True
                elif data.get("type") == "content":
                    full_response += data.get("content", "")
            except: pass

    if found_search_step:
        print("✅ SUCCESS: Agent triggered the internet_crawler_search tool.")
    else:
        print("❌ FAILURE: Agent did NOT trigger the search tool.")

    if len(full_response) > 50:
        print(f"✅ SUCCESS: Agent provided a response (Length: {len(full_response)}).")
        # print(f"Preview: {full_response[:200]}...")
    else:
        print("❌ FAILURE: Agent response is too short or empty.")

if __name__ == "__main__":
    asyncio.run(test_agent_internet_search())
