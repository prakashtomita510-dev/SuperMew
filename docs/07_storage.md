# 07. 数据与存储

## 7.1 存储总览

当前项目同时使用了 4 类存储：

1. 关系数据库
- PostgreSQL 或 SQLite

2. 缓存
- Redis 或进程内字典

3. 向量存储
- Milvus 或本地 JSON/Numpy mock

4. 文件存储
- `data/documents/`

## 7.2 关系数据库

### 目标设计

README 和 docker-compose 指向的主目标是 PostgreSQL：

- 数据库名：`langchain_app`
- 用户名：`postgres`
- 密码：`postgres`

### 本地默认回退

`backend/database.py` 默认值是：

```text
sqlite:///./supermew.db
```

这意味着如果没有显式配置 `DATABASE_URL`，应用会在当前工作目录生成 SQLite 文件。

### ORM 模型

#### `users`

字段：

- `id`
- `username`
- `password_hash`
- `role`
- `created_at`

#### `chat_sessions`

字段：

- `id`
- `user_id`
- `session_id`
- `metadata_json`
- `updated_at`
- `created_at`

约束：

- `(user_id, session_id)` 唯一

#### `chat_messages`

字段：

- `id`
- `session_ref_id`
- `message_type`
- `content`
- `timestamp`
- `rag_trace`

#### `parent_chunks`

字段：

- `chunk_id`
- `text`
- `filename`
- `file_type`
- `file_path`
- `page_number`
- `parent_chunk_id`
- `root_chunk_id`
- `chunk_level`
- `chunk_idx`
- `updated_at`

## 7.3 Redis / 内存缓存

### `backend/cache.py`

缓存类：

- `RedisCache`

配置：

- `REDIS_URL`
- `REDIS_KEY_PREFIX`
- `REDIS_CACHE_TTL_SECONDS`

当前缓存项：

1. 会话消息
- key: `supermew:chat_messages:{user}:{session}`

2. 会话列表
- key: `supermew:chat_sessions:{user}`

3. 父级 chunk
- key: `supermew:parent_chunk:{chunk_id}`

### 回退逻辑

若 Redis 不可连接：

- 自动回退到本地 `_cache_dict`

实测结果：

- 本地验证时 Redis 未连通，系统切到了内存缓存模式

局限：

- 进程重启后缓存丢失
- 多进程之间不共享
- 不适合作为真正生产缓存替代

## 7.4 向量存储

### 目标设计：Milvus

`backend/milvus_client.py` 设计了一套包含这些字段的 collection：

- `dense_embedding`
- `sparse_embedding`
- `text`
- `filename`
- `file_type`
- `file_path`
- `page_number`
- `chunk_idx`
- `chunk_id`
- `parent_chunk_id`
- `root_chunk_id`
- `chunk_level`

索引：

- dense: HNSW
- sparse: SPARSE_INVERTED_INDEX

### 实际回退：MockMilvus

若 `MILVUS_URI` 不是 `http...` 或真实 Milvus 不可连通：

- 进入 `AdvancedMockMilvusClient`
- 数据落到 `backend/mock_milvus_storage.json`
- 检索主要靠 Numpy 余弦相似度

实测结果：

- 本地验证时系统处于 mock 模式
- 输出里显示 `MILVUS_URI` 是本地路径形式，因此根本没有尝试连真实 Milvus

### 重要差异

mock 模式的 `hybrid_search()` 实际只是 dense search 代理，不是真正的 sparse+dense 融合。

这意味着：

- 本地可运行
- 但本地无法真实验证 hybrid retrieval 质量

## 7.5 文件存储

### 上传目录

- `data/documents/`

当前目录中可见已有样例：

- `test.pdf`
- `attention-is-all-you-need-Paper.pdf`
- 其他 PDF

### 行为

- 上传会把文件原样写入该目录
- 删除文档向量时，本地文件默认保留

## 7.6 前端本地存储

浏览器端只持久化一项：

- `localStorage['accessToken']`

不持久化：

- 会话内容
- 会话列表
- 文档列表

## 7.7 环境变量清单

### 模型与生成

- `ARK_API_KEY`
- `MODEL`
- `BASE_URL`
- `GRADE_MODEL`

### 向量与检索

- `EMBEDDER`
- `EMBEDDING_BASE_URL`
- `EMBEDDING_API_KEY`
- `RERANK_MODEL`
- `RERANK_BINDING_HOST`
- `RERANK_API_KEY`
- `AUTO_MERGE_ENABLED`
- `AUTO_MERGE_THRESHOLD`
- `LEAF_RETRIEVE_LEVEL`

### 基础设施

- `DATABASE_URL`
- `REDIS_URL`
- `MILVUS_HOST`
- `MILVUS_PORT`
- `MILVUS_COLLECTION`
- `MILVUS_URI`

### 安全与鉴权

- `JWT_SECRET_KEY`
- `ADMIN_INVITE_CODE`
- `JWT_ALGORITHM`
- `JWT_EXPIRE_MINUTES`
- `PASSWORD_PBKDF2_ROUNDS`

### 工具能力

- `AMAP_WEATHER_API`
- `AMAP_API_KEY`

### 进程监听

- `HOST`
- `PORT`

## 7.8 数据一致性逻辑

### 聊天消息

- 数据库存储是权威源
- Redis 只是加速层
- 保存会话后会写回消息缓存并清理会话列表缓存

### 父级 chunk

- 数据库存储是权威源
- Redis 缓存按 `chunk_id` 局部缓存

### 文档覆盖上传

上传同名文件时：

1. 先删 Milvus 向量
2. 再删 `parent_chunks`
3. 再重新写入

### 风险点

- 若上传过程中断，可能出现“部分已删、部分未重建”的窗口
- 没有事务把“向量存储 + 数据库写入 + 文件落盘”作为一个原子单元

## 7.9 当前存储设计的优缺点

优点：

- 关系数据和向量数据职责明确
- 会话、文档、父块都有可持久化落点
- 有本地回退能力，开发门槛低

缺点：

- SQLite / PostgreSQL 双模式容易混淆
- Milvus mock 与真实行为差距大
- BM25 稀疏状态管理不完整
- 仓库混入运行期数据文件，降低可交接性
