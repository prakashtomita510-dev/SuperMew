import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field

load_dotenv()

API_KEY = os.getenv("ARK_API_KEY")
MODEL = os.getenv("MODEL")
BASE_URL = os.getenv("BASE_URL")

class GradeDocuments(BaseModel):
    binary_score: str = Field(description="Relevance score: 'yes' or 'no'")

def test_grader():
    print(f"Testing MODEL: {MODEL} at {BASE_URL}")
    try:
        model = init_chat_model(
            model=MODEL,
            model_provider="openai",
            api_key=API_KEY,
            base_url=BASE_URL,
            temperature=0,
        )
        
        # Test basic invoke
        print("Testing simple invoke...")
        resp = model.invoke("Hello, are you there?")
        print(f"Response: {resp.content}")
        
        # Test structured output (this is where it usually fails)
        print("Testing structured output...")
        grader = model.with_structured_output(GradeDocuments)
        resp2 = grader.invoke("Is 'apple' a fruit? Answer in binary_score 'yes' or 'no'.")
        print(f"Structured Response: {resp2}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_grader()
