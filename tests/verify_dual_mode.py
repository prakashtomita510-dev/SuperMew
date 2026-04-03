import sys
import os

# Add backend to sys.path
current_dir = os.getcwd()
backend_dir = os.path.join(current_dir, 'backend')
sys.path.append(backend_dir)

from milvus_client import MilvusManager
from cache import cache

def test_dual_mode():
    print("=== SuperMew Dual-Mode Verification ===")
    
    # 1. Milvus Test
    print("\n[1] Testing Milvus...")
    manager = MilvusManager()
    manager._get_client()
    if manager.use_mock:
        print("💡 当前状态: 本地 Mock 模式 (Numpy + JSON)")
        print("   - 原因: 未检测到运行中的 Milvus 服务。")
    else:
        print("🚀 当前状态: 生产级模式 (MilvusClient)")
        print(f"   - 连接地址: {manager.uri}")
    
    # 2. Redis Test
    print("\n[2] Testing Redis...")
    if cache.use_mock:
        print("💡 当前状态: 本地 Mock 模式 (In-memory dict)")
        print("   - 原因: 未检测到运行中的 Redis 服务。")
    else:
        print("🚀 当前状态: 生产级模式 (Redis Server)")
        print(f"   - 连接地址: {cache.redis_url}")

    print("\n=== 验证完成 ===")

if __name__ == "__main__":
    test_dual_mode()
