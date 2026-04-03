from pymilvus import MilvusClient
import sys

uri = "milvus_test.db"
print(f"Testing MilvusClient with uri={uri}")
try:
    client = MilvusClient(uri=uri)
    print("Milvus Success")
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"Milvus Fail: {type(e).__name__}: {e}")
