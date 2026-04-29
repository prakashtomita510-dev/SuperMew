import os

path = r'd:\agent_demo\SuperMew\backend\embedding.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

target1 = 'self.embedder = os.getenv("EMBEDDER", "embedding-3-pro")'
replacement1 = 'self.embedder = os.getenv("EMBEDDER", "embedding-3-pro")\n        self.session = requests.Session()'

target2 = 'response = requests.post(f"{self.base_url}/embeddings", headers=headers, json=data)'
replacement2 = 'response = self.session.post(f"{self.base_url}/embeddings", headers=headers, json=data)'

if target1 in content:
    content = content.replace(target1, replacement1)
if target2 in content:
    content = content.replace(target2, replacement2)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Successfully updated embedding.py")
