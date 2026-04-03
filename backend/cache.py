import json
import os
from typing import Any, Optional

import redis


class RedisCache:
    """支持双模自适应的缓存类（Redis 或 内存字典）"""

    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.key_prefix = os.getenv("REDIS_KEY_PREFIX", "supermew")
        self.default_ttl = int(os.getenv("REDIS_CACHE_TTL_SECONDS", "300"))
        
        self.client = None
        self._cache_dict = {}
        self.use_mock = False

        try:
            print(f"正在尝试连接 Redis: {self.redis_url}...")
            self.client = redis.from_url(self.redis_url, socket_connect_timeout=2)
            self.client.ping()
            print("✅ 已连接到 Redis 服务。")
            self.use_mock = False
        except Exception as e:
            print(f"⚠️ 无法连接到 Redis ({e})，正在切换到本地内存缓存模式...")
            self.client = None
            self.use_mock = True

    def _key(self, key: str) -> str:
        return f"{self.key_prefix}:{key}"

    def get_json(self, key: str) -> Optional[Any]:
        full_key = self._key(key)
        if not self.use_mock and self.client:
            try:
                data = self.client.get(full_key)
                return json.loads(data) if data else None
            except:
                pass
        return self._cache_dict.get(full_key)

    def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        full_key = self._key(key)
        if not self.use_mock and self.client:
            try:
                self.client.set(full_key, json.dumps(value), ex=ttl or self.default_ttl)
                return
            except:
                pass
        self._cache_dict[full_key] = value

    def delete(self, key: str) -> None:
        full_key = self._key(key)
        if not self.use_mock and self.client:
            try:
                self.client.delete(full_key)
            except:
                pass
        self._cache_dict.pop(full_key, None)

    def delete_pattern(self, pattern: str) -> None:
        full_pattern = self._key(pattern)
        if not self.use_mock and self.client:
            try:
                keys = self.client.keys(full_pattern)
                if keys:
                    self.client.delete(*keys)
                return
            except:
                pass
        
        # simplistic pattern matching for mock
        prefixes = [k for k in self._cache_dict.keys() if k.startswith(full_pattern.replace('*', ''))]
        for k in prefixes:
            self._cache_dict.pop(k, None)


cache = RedisCache()
