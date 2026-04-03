import sys
import os
from dotenv import load_dotenv

# Add backend to sys.path
current_dir = os.getcwd()
backend_dir = os.path.join(current_dir, 'backend')
sys.path.append(backend_dir)

from document_loader import DocumentLoader

def test_token_loader():
    print("Testing Token-based DocumentLoader...")
    loader = DocumentLoader()
    
    test_file = os.path.join(current_dir, "data", "documents", "test.pdf")
    if not os.path.exists(test_file):
        print(f"❌ ERROR: Test file not found at {test_file}")
        return

    print(f"Loading and splitting: {test_file}")
    try:
        chunks = loader.load_document(test_file, "test.pdf")
        print(f"✅ SUCCESS: Loaded {len(chunks)} chunks.")
        
        # Check some chunks
        for i in range(min(3, len(chunks))):
            chunk = chunks[i]
            tokens = len(loader.encoding.encode(chunk['text']))
            print(f"Chunk {i} [Level {chunk['chunk_level']}]: {tokens} tokens")
            
        # Verify hierarchical structure
        has_l1 = any(c['chunk_level'] == 1 for c in chunks)
        has_l3 = any(c['chunk_level'] == 3 for c in chunks)
        if has_l1 and has_l3:
            print("✅ SUCCESS: Hierarchical levels (L1, L3) detected.")
        else:
            print(f"❌ FAILURE: Missing hierarchical levels. L1: {has_l1}, L3: {has_l3}")

    except Exception as e:
        print(f"❌ ERROR during processing: {e}")

if __name__ == "__main__":
    test_token_loader()
