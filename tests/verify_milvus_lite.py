import sys
import os
import time

# Add backend to sys.path
current_dir = os.getcwd()
backend_dir = os.path.join(current_dir, 'backend')
sys.path.append(backend_dir)

from milvus_client import MilvusManager
from embedding import EmbeddingService

def test_milvus_lite():
    print("Testing Milvus Lite Migration...")
    
    # Cleanup old milkvus db if exists
    if os.path.exists("./milvus_supermew.db"):
        print("Cleaning up old milvus.db...")
        # Close any existing connections if possible, but here we just try to delete
        # Actually, it's safer to just use a new name or drop collection
    
    manager = MilvusManager()
    embedding_svc = EmbeddingService()
    
    try:
        print("Initializing collection...")
        # manager.drop_collection() # 被禁用，防止误删用户文档
        manager.init_collection(dense_dim=1536)
        
        print("Inserting test data...")
        text = "DeepSeek-R1 is a powerful open-source reasoning model."
        dense_vec = embedding_svc.get_embeddings([text])[0]
        sparse_vec = embedding_svc.get_sparse_embedding(text)
        
        data = [{
            "dense_embedding": dense_vec,
            "sparse_embedding": sparse_vec,
            "text": text,
            "filename": "test_reasoning.pdf",
            "file_type": "PDF",
            "chunk_id": "test_1",
            "chunk_level": 3
        }]
        
        manager.insert(data)
        print("✅ Insert successful.")
        
        # Search
        print("Searching for 'reasoning model'...")
        q_text = "reasoning model"
        q_dense = embedding_svc.get_embeddings([q_text])[0]
        q_sparse = embedding_svc.get_sparse_embedding(q_text)
        
        # Test dense retrieve first
        print("Testing dense retrieve...")
        results = manager.dense_retrieve(q_dense, top_k=1)
        if results and results[0]['text'] == text:
            print(f"✅ Dense search successful: {results[0]['text']}")
        else:
            print(f"❌ Dense search failed: {results}")

        # Test hybrid retrieve
        print("Testing hybrid retrieve...")
        h_results = manager.hybrid_retrieve(q_dense, q_sparse, top_k=1)
        if h_results and h_results[0]['text'] == text:
            print(f"✅ Hybrid search successful: {h_results[0]['text']}")
        else:
            print(f"❌ Hybrid search failed: {h_results}")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_milvus_lite()
