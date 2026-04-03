"""Milvus 客户端 - 支持密集向量+稀疏向量混合检索"""
import os
import json
import numpy as np
from typing import Any
from dotenv import load_dotenv

load_dotenv()

class DataType:
    INT64 = 5
    FLOAT_VECTOR = 101
    SPARSE_FLOAT_VECTOR = 104
    VARCHAR = 21

class AnnSearchRequest:
    def __init__(self, data, anns_field, param, limit, expr=None):
        self.data = data
        self.anns_field = anns_field
        self.param = param
        self.limit = limit
        self.expr = expr

class RRFRanker:
    def __init__(self, k=60):
        self.k = k


class MilvusManager:
    """Milvus 客户端 - 支持双模自适应（生产级 MilvusClient 或 高仿真 Numpy Mock）"""

    def __init__(self):
        self.host = os.getenv("MILVUS_HOST", "127.0.0.1")
        self.port = os.getenv("MILVUS_PORT", "19530")
        self.collection_name = os.getenv("MILVUS_COLLECTION", "embeddings_collection")
        self.uri = os.getenv("MILVUS_URI", f"http://{self.host}:{self.port}")
        self.client = None
        self.use_mock = False

    def _get_client(self) -> Any:
        if self.client is not None:
            return self.client

        # 尝试连接真实 Milvus - 仅当 URI 是网络地址时尝试，避免本地文件路径触发 Milvus-lite 挂起
        if self.uri.startswith("http"):
            try:
                from pymilvus import MilvusClient, DataType, AnnSearchRequest, RRFRanker
                print(f"正在尝试连接生产级 Milvus: {self.uri}...")
                client = MilvusClient(uri=self.uri, timeout=3)
                # 简单测试连接
                client.list_collections()
                print("✅ 已连接到生产级 Milvus 服务。")
                self.client = client
                self.use_mock = False
                return self.client
            except Exception as e:
                print(f"⚠️ 无法连接到 Milvus ({e})，正在切换到本地高性能 Mock 模式 (Numpy)...")
        else:
            print(f"ℹ️ 检测到本地 URI ({self.uri})，直接进入本地高性能 Mock 模式 (Numpy)...")
            
        self.use_mock = True

        class AdvancedMockMilvusClient:
            def __init__(self, *args, **kwargs):
                self.storage_file = os.path.join(os.path.dirname(__file__), "mock_milvus_storage.json")
                if not os.path.exists(self.storage_file):
                    with open(self.storage_file, "w", encoding="utf-8") as f:
                        json.dump([], f)

            def _load(self):
                try:
                    with open(self.storage_file, "r", encoding="utf-8") as f:
                        return json.load(f)
                except: return []

            def _save(self, data):
                with open(self.storage_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)

            def has_collection(self, *args, **kwargs): return True
            def create_schema(self, *args, **kwargs):
                class Schema:
                    def add_field(self, *args, **kwargs): pass
                return Schema()
            def prepare_index_params(self, *args, **kwargs):
                class Params:
                    def add_index(self, *args, **kwargs): pass
                return Params()
            def create_collection(self, *args, **kwargs): pass

            def insert(self, collection_name, data, *args, **kwargs):
                current = self._load()
                current.extend(data)
                self._save(current)
                return {"insert_count": len(data)}

            def query(self, collection_name, filter="", output_fields=None, limit=1000, *args, **kwargs):
                data = self._load()
                if 'filename == "' in (filter or ""):
                    import re
                    match = re.search(r'filename == "(.*?)"', filter)
                    if match:
                        fname = match.group(1)
                        data = [d for d in data if d.get("filename") == fname]
                
                # Handling "chunk_id in [...]" for auto-merging
                if 'chunk_id in [' in (filter or ""):
                    import re
                    ids_str = re.search(r'chunk_id in \[(.*?)\]', filter).group(1)
                    ids = [id.strip().strip('"').strip("'") for id in ids_str.split(',')]
                    data = [d for d in data if d.get("chunk_id") in ids]

                # Limit output fields
                if output_fields:
                    result = []
                    for d in data:
                        result.append({k: v for k, v in d.items() if k in output_fields})
                    return result[:limit]
                return data[:limit]

            def search(self, collection_name, data, limit=5, filter="", output_fields=None, *args, **kwargs):
                """真正计算余弦相似度"""
                query_vector = np.array(data[0])
                all_data = self._load()
                
                # Optional: Filtering
                if filter and 'filename == "' in filter:
                    import re
                    match = re.search(r'filename == "(.*?)"', filter)
                    if match:
                        fname = match.group(1)
                        all_data = [d for d in all_data if d.get("filename") == fname]

                # Compute similarities
                hits = []
                for idx, item in enumerate(all_data):
                    target_vector = np.array(item.get("dense_embedding", []))
                    if target_vector.size == 0 or target_vector.shape != query_vector.shape:
                        continue
                        
                    # Cosine Similarity = (A . B) / (||A|| * ||B||)
                    norm_a = np.linalg.norm(query_vector)
                    norm_b = np.linalg.norm(target_vector)
                    if norm_a == 0 or norm_b == 0:
                        sim = 0
                    else:
                        sim = np.dot(query_vector, target_vector) / (norm_a * norm_b)
                    
                    hits.append({
                        "id": idx,
                        "distance": float(sim),
                        "entity": item
                    })

                # Sort by similarity descending
                hits.sort(key=lambda x: x["distance"], reverse=True)
                
                class MockHit:
                    def __init__(self, h):
                        self.id = h["id"]
                        self.distance = h["distance"]
                        self.entity = h["entity"]
                    def get(self, key, default=None):
                        if key == "entity": return self.entity
                        return self.entity.get(key, default)

                return [[MockHit(h) for h in hits[:limit]]]

            def hybrid_search(self, collection_name, reqs, limit=5, output_fields=None, *args, **kwargs):
                # Use the dense search as hybrid search surrogate for now
                dense_req = reqs[0]
                return self.search(collection_name, dense_req.data, limit=limit, filter=dense_req.expr, output_fields=output_fields)

            def delete(self, collection_name, filter="", *args, **kwargs):
                if 'filename == "' in (filter or ""):
                    import re
                    match = re.search(r'filename == "(.*?)"', filter)
                    if match:
                        fname = match.group(1)
                        data = self._load()
                        new_data = [d for d in data if d.get("filename") != fname]
                        self._save(new_data)
                        return {"delete_count": len(data) - len(new_data)}
                return {"delete_count": 0}

            def drop_collection(self, *args, **kwargs):
                self._save([])

        if self.client is None:
            self.client = AdvancedMockMilvusClient()
        return self.client

    def init_collection(self, dense_dim: int = 1536):
        """
        初始化 Milvus 集合 - 同时支持密集向量和稀疏向量
        :param dense_dim: 密集向量维度（默认 1536，对应 embedding-3-pro）
        """
        client = self._get_client()
        if not client.has_collection(self.collection_name):
            schema = client.create_schema(auto_id=True, enable_dynamic_field=True)
            
            # 主键
            schema.add_field("id", DataType.INT64, is_primary=True, auto_id=True)
            
            # 密集向量（来自 embedding 模型）
            schema.add_field("dense_embedding", DataType.FLOAT_VECTOR, dim=dense_dim)
            
            # 稀疏向量（来自 BM25）
            schema.add_field("sparse_embedding", DataType.SPARSE_FLOAT_VECTOR)
            
            # 文本和元数据字段
            schema.add_field("text", DataType.VARCHAR, max_length=15000)
            schema.add_field("filename", DataType.VARCHAR, max_length=255)
            schema.add_field("file_type", DataType.VARCHAR, max_length=50)
            schema.add_field("file_path", DataType.VARCHAR, max_length=1024)
            schema.add_field("page_number", DataType.INT64)
            schema.add_field("chunk_idx", DataType.INT64)

            # Auto-merging 所需层级字段
            schema.add_field("chunk_id", DataType.VARCHAR, max_length=512)
            schema.add_field("parent_chunk_id", DataType.VARCHAR, max_length=512)
            schema.add_field("root_chunk_id", DataType.VARCHAR, max_length=512)
            schema.add_field("chunk_level", DataType.INT64)

            # 为两种向量分别创建索引
            index_params = client.prepare_index_params()
            
            # 密集向量索引 - 使用 HNSW
            index_params.add_index(
                field_name="dense_embedding",
                index_type="HNSW",
                metric_type="IP",
                params={"M": 16, "efConstruction": 256}
            )
            
            # 稀疏向量索引
            index_params.add_index(
                field_name="sparse_embedding",
                index_type="SPARSE_INVERTED_INDEX",
                metric_type="IP",
                params={"drop_ratio_build": 0.2}
            )

            client.create_collection(
                collection_name=self.collection_name,
                schema=schema,
                index_params=index_params
            )

    def insert(self, data: list[dict]):
        """插入数据到 Milvus"""
        return self._get_client().insert(self.collection_name, data)

    def query(self, filter_expr: str = "", output_fields: list[str] = None, limit: int = 10000):
        """查询数据"""
        return self._get_client().query(
            collection_name=self.collection_name,
            filter=filter_expr,
            output_fields=output_fields or ["filename", "file_type"],
            limit=limit
        )

    def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[dict]:
        """根据 chunk_id 批量查询分块（用于 Auto-merging 拉取父块）"""
        ids = [item for item in chunk_ids if item]
        if not ids:
            return []
        quoted_ids = ", ".join([f'"{item}"' for item in ids])
        filter_expr = f"chunk_id in [{quoted_ids}]"
        return self.query(
            filter_expr=filter_expr,
            output_fields=[
                "text",
                "filename",
                "file_type",
                "page_number",
                "chunk_id",
                "parent_chunk_id",
                "root_chunk_id",
                "chunk_level",
                "chunk_idx",
            ],
            limit=len(ids),
        )

    def hybrid_retrieve(
        self,
        dense_embedding: list[float],
        sparse_embedding: dict,
        top_k: int = 5,
        rrf_k: int = 60,     #可调节
        filter_expr: str = "",
    ) -> list[dict]:
        """
        混合检索 - 使用 RRF 融合密集向量和稀疏向量的检索结果
        
        :param dense_embedding: 密集向量
        :param sparse_embedding: 稀疏向量 {index: value, ...}
        :param top_k: 返回结果数量
        :param rrf_k: RRF 算法参数 k，默认60
        :return: 检索结果列表
        """
        output_fields = [
            "text",
            "filename",
            "file_type",
            "page_number",
            "chunk_id",
            "parent_chunk_id",
            "root_chunk_id",
            "chunk_level",
            "chunk_idx",
        ]
        
        # 密集向量搜索请求
        dense_search = AnnSearchRequest(
            data=[dense_embedding],
            anns_field="dense_embedding",
            param={"metric_type": "IP", "params": {"ef": 64}},
            limit=top_k * 2,  # 多取一些用于融合
            expr=filter_expr,
        )
        
        # 稀疏向量搜索请求
        sparse_search = AnnSearchRequest(
            data=[sparse_embedding],
            anns_field="sparse_embedding",
            param={"metric_type": "IP", "params": {"drop_ratio_search": 0.2}},
            limit=top_k * 2,
            expr=filter_expr,
        )
        
        # 使用 RRF 排序算法融合结果
        reranker = RRFRanker(k=rrf_k)
        
        results = self._get_client().hybrid_search(
            collection_name=self.collection_name,
            reqs=[dense_search, sparse_search],
            ranker=reranker,
            limit=top_k,
            output_fields=output_fields
        )
        
        # 格式化返回结果
        formatted_results = []
        for hits in results:
            for hit in hits:
                formatted_results.append({
                    "id": hit.get("id"),
                    "text": hit.get("text", ""),
                    "filename": hit.get("filename", ""),
                    "file_type": hit.get("file_type", ""),
                    "page_number": hit.get("page_number", 0),
                    "chunk_id": hit.get("chunk_id", ""),
                    "parent_chunk_id": hit.get("parent_chunk_id", ""),
                    "root_chunk_id": hit.get("root_chunk_id", ""),
                    "chunk_level": hit.get("chunk_level", 0),
                    "chunk_idx": hit.get("chunk_idx", 0),
                    "score": hit.get("distance", 0.0)
                })
        
        return formatted_results

    def dense_retrieve(self, dense_embedding: list[float], top_k: int = 5, filter_expr: str = "") -> list[dict]:
        """
        仅使用密集向量检索（降级模式，用于稀疏向量不可用时）
        """
        results = self._get_client().search(
            collection_name=self.collection_name,
            data=[dense_embedding],
            anns_field="dense_embedding",
            search_params={"metric_type": "IP", "params": {"ef": 64}},
            limit=top_k,
            output_fields=[
                "text",
                "filename",
                "file_type",
                "page_number",
                "chunk_id",
                "parent_chunk_id",
                "root_chunk_id",
                "chunk_level",
                "chunk_idx",
            ],
            filter=filter_expr,
        )
        
        formatted_results = []
        for hits in results:
            for hit in hits:
                formatted_results.append({
                    "id": hit.get("id"),
                    "text": hit.get("text", ""),
                    "filename": hit.get("filename", ""),
                    "file_type": hit.get("file_type", ""),
                    "page_number": hit.get("page_number", 0),
                    "chunk_id": hit.get("chunk_id", ""),
                    "parent_chunk_id": hit.get("parent_chunk_id", ""),
                    "root_chunk_id": hit.get("root_chunk_id", ""),
                    "chunk_level": hit.get("chunk_level", 0),
                    "chunk_idx": hit.get("chunk_idx", 0),
                    "score": hit.get("distance", 0.0)
                })
        
        return formatted_results

    def delete(self, filter_expr: str):
        """删除数据"""
        return self._get_client().delete(
            collection_name=self.collection_name,
            filter=filter_expr
        )

    def has_collection(self) -> bool:
        """检查集合是否存在"""
        return self._get_client().has_collection(self.collection_name)

    def drop_collection(self):
        """删除集合（用于重建 schema）"""
        client = self._get_client()
        if client.has_collection(self.collection_name):
            client.drop_collection(self.collection_name)


# 全局 Mock 类定义（用于在 Mock 模式下支持 DataType 等）
if not globals().get("DataType"):
    class DataType:
        INT64 = 5
        FLOAT_VECTOR = 101
        SPARSE_FLOAT_VECTOR = 104
        VARCHAR = 21

    class AnnSearchRequest:
        def __init__(self, data, anns_field, param, limit, expr=None):
            self.data = data
            self.anns_field = anns_field
            self.param = param
            self.limit = limit
            self.expr = expr

    class RRFRanker:
        def __init__(self, k=60):
            self.k = k
