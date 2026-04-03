import sqlite3
import os

db_path = r"c:\Users\Administrator\Desktop\agent_demo\SuperMew\backend\supermew.db"

if not os.path.exists(db_path):
    print("Database file not found.")
else:
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, role FROM users")
        rows = cursor.fetchall()
        if not rows:
            print("No users found.")
        else:
            print("ID | Username | Role")
            print("-" * 30)
            for row in rows:
                print(f"{row[0]} | {row[1]} | {row[2]}")
        conn.close()
    except Exception as e:
        print(f"Error querying database: {e}")
