import os

path = r'd:\agent_demo\SuperMew\backend\milvus_writer.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

target = '"chunk_level": doc.get("chunk_level", 0),'
replacement = '"chunk_level": doc.get("chunk_level", 0),\n                    "pid": doc.get("pid", ""),'

if target in content:
    content = content.replace(target, replacement)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Successfully updated milvus_writer.py")
else:
    print("Target string not found!")

# Also fix milvus_client.py
client_path = r'd:\agent_demo\SuperMew\backend\milvus_client.py'
with open(client_path, 'r', encoding='utf-8') as f:
    client_content = f.read()

# Update output_fields
target_of = '"chunk_idx",\n            ]' # Using this broad match to avoid indent issues
if target_of not in client_content:
    # try with different indentation or commas
    target_of = '"chunk_idx",'

replacement_of = '"chunk_idx",\n                "pid",'

# Update dict constructor
target_dict = '"chunk_idx": hit.get("chunk_idx", 0),\n                    "score": hit.get("distance", 0.0)'
replacement_dict = '"chunk_idx": hit.get("chunk_idx", 0),\n                    "pid": hit.get("pid", ""),\n                    "score": hit.get("distance", 0.0)'

if target_dict in client_content:
    client_content = client_content.replace(target_dict, replacement_dict)
    # Also update output_fields (careful here as it appears thrice)
    client_content = client_content.replace('"chunk_idx",', '"chunk_idx",\n                "pid",')
    with open(client_path, 'w', encoding='utf-8') as f:
        f.write(client_content)
    print("Successfully updated milvus_client.py")
else:
    print("Target string in milvus_client.py not found!")
