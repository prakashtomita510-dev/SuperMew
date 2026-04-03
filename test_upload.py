import requests
import os

# Test registration/login to get token
BASE_URL = "http://localhost:8000"
ADMIN_INVITE_CODE = "supermew-admin-2026"

username = "uploader_test"
password = "Password123!"

# Register
resp = requests.post(f"{BASE_URL}/auth/register", json={
    "username": username,
    "password": password,
    "role": "admin",
    "admin_code": ADMIN_INVITE_CODE
})
if resp.status_code == 409: # Already exists
    # Login
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "username": username,
        "password": password
    })

token = resp.json().get("access_token")
headers = {"Authorization": f"Bearer {token}"}

# Create a dummy text file to upload (renamed to .txt then .pdf doesn't work well for loaders, I'll use the existing test.pdf)
file_path = r"C:\Users\Administrator\Desktop\agent_demo\test.pdf"

print(f"Uploading {file_path}...")
with open(file_path, "rb") as f:
    files = {"file": f}
    resp = requests.post(f"{BASE_URL}/documents/upload", headers=headers, files=files)

print(f"Status: {resp.status_code}")
print(f"Response: {resp.text}")
