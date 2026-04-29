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

    def dict(self):
        return {"strategy": "rrf", "params": {"k": self.k}}


class WeightedRanker:
    def __init__(self, *weights):
        self.weights = list(weights)

    def dict(self):
        return {"strategy": "weighted", "params": {"weights": self.weights}}


class MilvusManager:
    """Milvus 客户端 - 支持双模自适应（生产级 MilvusClient 或 高仿真 Numpy Mock）"""

    def __init__(self, host=None, port=None, collection_name=None, uri=None):
        self.host = host or os.getenv("MILVUS_HOST", "127.0.0.1")
        self.port = port or os.getenv("MILVUS_PORT", "19530")
        self.collection_name = collection_name or os.getenv("MILVUS_COLLECTION", "embeddings_collection")
        self.uri = uri or os.getenv("MILVUS_URI", f"http://{self.host}:{self.port}")
        self.client = None
        self.use_mock = False
        self.require_real = os.getenv("MILVUS_REQUIRE_REAL", "false").lower() == "true"

    def _get_client(self) -> Any:
        if self.client is not None:
            return self.client

        # 尝试连接真实 Milvus
        if self.uri.startswith("http"):
            try:
                from pymilvus import MilvusClient
                print(f"正在尝试连接生产级 Milvus: {self.uri}...")
                client = MilvusClient(uri=self.uri, timeout=3)
                client.list_collections()
                print("✅ 已连接到生产级 Milvus 服务。")
                self.client = client
                self.use_mock = False
                return self.client
            except Exception as e:
                if self.require_real:
                    raise RuntimeError(f"MILVUS_REQUIRE_REAL=true，但无法连接真实 Milvus: {e}") from e
                print(f"⚠️ 无法连接到 Milvus ({e})，正在切换到本地高性能 Mock 模式 (Numpy)...")
        else:
            if self.require_real:
                raise RuntimeError(f"MILVUS_REQUIRE_REAL=true，但当前 MILVUS_URI={self.uri} 不是可连接的真实服务地址。")
            print(f"ℹ️ 检测到本地 URI ({self.uri})，直接进入本地高性能 Mock 模式 (Numpy)...")
            
        self.use_mock = True

        class AdvancedMockMilvusClient:
            def __init__(self, storage_uri):
                # 如果 URI 是 .db 则改成 .json 方便观察，或者直接按原样
                self.storage_file = storage_uri if "mock" in storage_uri.lower() else "mock_milvus_storage.json"
                # 为了防止相对路径问题，强制放到当前工作目录或 backend 目录下
                if not os.path.dirname(self.storage_file):
                    self.storage_file = os.path.join(os.getcwd(), self.storage_file)
                
                self._cache = None
                
                if not os.path.exists(self.storage_file):
                    with open(self.storage_file, "w", encoding="utf-8") as f:
                        json.dump([], f)

            def _load(self):
                if self._cache is not None:
                    return self._cache
                try:
                    with open(self.storage_file, "r", encoding="utf-8") as f:
                        self._cache = json.load(f)
                        return self._cache
                except: return []

            def _save(self, data):
                self._cache = data
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
                # 简单过滤支持 (filename == "xxx" or chunk_id in [...])
                if 'filename == "' in (filter or ""):
                    import re
                    match = re.search(r'filename == "(.*?)"', filter)
                    if match:
                        fname = match.group(1)
                        data = [d for d in data if d.get("filename") == fname]
                
                if 'chunk_id in [' in (filter or ""):
                    import re
                    match = re.search(r'chunk_id in \[(.*?)\]', filter)
                    if match:
                        ids_str = match.group(1)
                        ids = [id.strip().strip('"').strip("'") for id in ids_str.split(',')]
                        data = [d for d in data if d.get("chunk_id") in ids]
                
                if 'chunk_level ==' in (filter or ""):
                    import re
                    match = re.search(r'chunk_level == (\d+)', filter)
                    if match:
                        lvl = int(match.group(1))
                        data = [d for d in data if d.get("chunk_level") == lvl]
                
                if 'page_number ==' in (filter or ""):
                    import re
                    match = re.search(r'page_number == (\d+)', filter)
                    if match:
                        pnum = int(match.group(1))
                        data = [d for d in data if d.get("page_number") == pnum]

                if output_fields:
                    result = []
                    for d in data:
                        res_item = {k: v for k, v in d.items() if k in output_fields}
                        # Mock search usually returns idx as id
                        res_item["id"] = 0 
                        result.append(res_item)
                    return result[:limit]
                return data[:limit]

            def search(self, collection_name, data, limit=5, filter="", output_fields=None, *args, **kwargs):
                all_data = self._load()
                
                # Apply filter
                filtered_data = all_data
                if filter:
                    if 'chunk_level ==' in filter:
                        import re
                        match = re.search(r'chunk_level == (\d+)', filter)
                        if match:
                            lvl = int(match.group(1))
                            filtered_data = [d for d in all_data if d.get("chunk_level") == lvl]
                    
                    if 'page_number ==' in filter:
                        import re
                        match = re.search(r'page_number == (\d+)', filter)
                        if match:
                            pnum = int(match.group(1))
                            filtered_data = [d for d in filtered_data if d.get("page_number") == pnum]

                query_vec = data[0]
                hits = []
                
                is_sparse = isinstance(query_vec, dict)
                
                if is_sparse:
                    # Sparse Dot Product
                    for idx, item in enumerate(filtered_data):
                        target_sparse = item.get("sparse_embedding", {})
                        if not isinstance(target_sparse, dict): continue

                        normalized_query = {str(k): float(v) for k, v in query_vec.items()}
                        normalized_target = {str(k): float(v) for k, v in target_sparse.items()}
                        score = sum(normalized_query.get(k, 0.0) * normalized_target.get(k, 0.0) for k in normalized_query)
                        if score > 0:
                            hits.append({"id": idx, "distance": float(score), "entity": item})
                else:
                    # Dense Cosine Similarity (Vectorized)
                    query_np = np.array(query_vec)
                    norm_q = np.linalg.norm(query_np)
                    if norm_q == 0: return [[]]
                    
                    target_vectors = []
                    valid_items = []
                    for item in filtered_data:
                        v = item.get("dense_embedding")
                        if v and len(v) == len(query_vec):
                            target_vectors.append(v)
                            valid_items.append(item)
                    
                    if not target_vectors: return [[]]
                    
                    targets_np = np.array(target_vectors)
                    # Dot products
                    dots = np.dot(targets_np, query_np)
                    # Norms
                    norms_t = np.linalg.norm(targets_np, axis=1)
                    
                    scores = dots / (norm_q * norms_t)
                    # Handle division by zero
                    scores = np.nan_to_num(scores)
                    
                    for i, score in enumerate(scores):
                        hits.append({"id": i, "distance": float(score), "entity": valid_items[i]})

                hits.sort(key=lambda x: x["distance"], reverse=True)
                
                class MockHit:
                    def __init__(self, h):
                        self.id = h["id"]
                        self.distance = h["distance"]
                        self.entity = h["entity"]
                    def get(self, key, default=None):
                        if key == "distance": return self.distance
                        if key == "id": return self.id
                        return self.entity.get(key, default)

                return [[MockHit(h) for h in hits[:limit]]]

            def hybrid_search(self, collection_name, reqs, limit=5, output_fields=None, ranker=None, *args, **kwargs):
                # RRF or Weighted Merge
                all_hits = []
                for req in reqs:
                    hits = self.search(collection_name, req.data, limit=limit*10, filter=req.expr, output_fields=output_fields)
                    all_hits.append(hits[0])
                
                if len(all_hits) == 1:
                    return [all_hits[0][:limit]]
                
                scores = {} # (chunk_id) -> score
                doc_map = {}
                strategy = getattr(ranker, 'strategy', 'rrf') if hasattr(ranker, 'strategy') else 'rrf'
                if not hasattr(ranker, 'strategy') and ranker:
                    # Check if it has 'k' or 'weights'
                    if hasattr(ranker, 'k'): strategy = 'rrf'
                    elif hasattr(ranker, 'weights'): strategy = 'weighted'

                if strategy == 'weighted':
                    weights = getattr(ranker, 'weights', [0.5, 0.5])
                    for i, hit_list in enumerate(all_hits):
                        w = weights[i] if i < len(weights) else 0.0
                        for hit in hit_list:
                            cid = hit.get("chunk_id")
                            if not cid: continue
                            scores[cid] = scores.get(cid, 0) + (hit.distance * w)
                            doc_map[cid] = hit.entity
                else:
                    # Simple RRF Implementation
                    rrf_k = getattr(ranker, 'k', 60) if ranker else 60
                    for hit_list in all_hits:
                        for rank, hit in enumerate(hit_list, 1):
                            cid = hit.get("chunk_id")
                            if not cid: continue
                            scores[cid] = scores.get(cid, 0) + (1.0 / (rrf_k + rank))
                            doc_map[cid] = hit.entity
                
                sorted_cids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
                
                class MockHit:
                    def __init__(self, cid, score, entity):
                        self.id = cid
                        self.distance = score
                        self.entity = entity
                    def get(self, key, default=None):
                        if key == "distance": return self.distance
                        if key == "id": return self.id
                        return self.entity.get(key, default)
                
                final_hits = [MockHit(cid, scores[cid], doc_map[cid]) for cid in sorted_cids[:limit]]
                return [final_hits]

            def delete(self, collection_name, filter="", *args, **kwargs):
                return {"delete_count": 0}

            def drop_collection(self, *args, **kwargs):
                self._save([])

        if self.client is None:
            self.client = AdvancedMockMilvusClient(self.uri)
        return self.client

    def init_collection(self, dense_dim: int = 1536):
        client = self._get_client()
        if not client.has_collection(self.collection_name):
            from pymilvus import DataType # Use real DataType if available
            schema = client.create_schema(auto_id=True, enable_dynamic_field=True)
            schema.add_field("id", DataType.INT64, is_primary=True, auto_id=True)
            schema.add_field("dense_embedding", DataType.FLOAT_VECTOR, dim=dense_dim)
            schema.add_field("sparse_embedding", DataType.SPARSE_FLOAT_VECTOR)
            schema.add_field("text", DataType.VARCHAR, max_length=15000)
            schema.add_field("filename", DataType.VARCHAR, max_length=255)
            schema.add_field("file_type", DataType.VARCHAR, max_length=50)
            schema.add_field("page_number", DataType.INT64)
            schema.add_field("chunk_id", DataType.VARCHAR, max_length=512)
            schema.add_field("parent_chunk_id", DataType.VARCHAR, max_length=512)
            schema.add_field("root_chunk_id", DataType.VARCHAR, max_length=512)
            schema.add_field("chunk_level", DataType.INT64)
            schema.add_field("chunk_idx", DataType.INT64)
            schema.add_field("pid", DataType.VARCHAR, max_length=255)

            index_params = client.prepare_index_params()
            index_params.add_index(field_name="dense_embedding", index_type="HNSW", metric_type="IP", params={"M": 16, "efConstruction": 256})
            index_params.add_index(field_name="sparse_embedding", index_type="SPARSE_INVERTED_INDEX", metric_type="IP")
            client.create_collection(collection_name=self.collection_name, schema=schema, index_params=index_params)

    def insert(self, data: list[dict]):
        return self._get_client().insert(self.collection_name, data)

    def query(self, filter_expr: str = "", output_fields=None, limit: int = 10000):
        effective_limit = limit
        if not self.use_mock:
            effective_limit = min(int(limit), 16384)
        return self._get_client().query(collection_name=self.collection_name, filter=filter_expr, output_fields=output_fields, limit=effective_limit)

    def hybrid_retrieve(self, dense_embedding, sparse_embedding, top_k=5, rrf_k=60, weights=None, filter_expr=""):
        output_fields = ["text", "filename", "file_type", "page_number", "chunk_id", "parent_chunk_id", "root_chunk_id", "chunk_level", "chunk_idx", "pid"]
        from milvus_client import AnnSearchRequest, RRFRanker, WeightedRanker
        dense_search = AnnSearchRequest(data=[dense_embedding], anns_field="dense_embedding", param={"metric_type": "IP", "params": {"ef": 64}}, limit=top_k * 2, expr=filter_expr)
        sparse_search = AnnSearchRequest(data=[sparse_embedding], anns_field="sparse_embedding", param={"metric_type": "IP"}, limit=top_k * 2, expr=filter_expr)
        
        if weights and isinstance(weights, (list, tuple)):
            reranker = WeightedRanker(*weights)
        else:
            reranker = RRFRanker(k=rrf_k)
            
        results = self._get_client().hybrid_search(collection_name=self.collection_name, reqs=[dense_search, sparse_search], ranker=reranker, limit=top_k, output_fields=output_fields)
        return self._format_results(results[0])

    def sparse_retrieve(self, sparse_embedding, top_k=5, filter_expr=""):
        output_fields = ["text", "filename", "file_type", "page_number", "chunk_id", "parent_chunk_id", "root_chunk_id", "chunk_level", "chunk_idx", "pid"]
        from milvus_client import AnnSearchRequest, RRFRanker
        sparse_search = AnnSearchRequest(data=[sparse_embedding], anns_field="sparse_embedding", param={"metric_type": "IP"}, limit=top_k, expr=filter_expr)
        results = self._get_client().hybrid_search(collection_name=self.collection_name, reqs=[sparse_search], ranker=RRFRanker(k=60), limit=top_k, output_fields=output_fields)
        return self._format_results(results[0])

    def dense_retrieve(self, dense_embedding, top_k=5, filter_expr=""):
        output_fields = ["text", "filename", "file_type", "page_number", "chunk_id", "parent_chunk_id", "root_chunk_id", "chunk_level", "chunk_idx", "pid"]
        results = self._get_client().search(collection_name=self.collection_name, data=[dense_embedding], anns_field="dense_embedding", search_params={"metric_type": "IP"}, limit=top_k, output_fields=output_fields, filter=filter_expr)
        return self._format_results(results[0])

    def _format_results(self, hits):
        formatted = []
        for hit in hits:
            if isinstance(hit, dict):
                entity = hit.get("entity") if isinstance(hit.get("entity"), dict) else {}
                getter = lambda key, default=None: entity.get(key, hit.get(key, default))
                hit_id = hit.get("id")
            else:
                getter = lambda key, default=None: hit.get(key, default)
                hit_id = getattr(hit, "id", getter("id"))
            formatted.append({
                "id": hit_id,
                "text": getter("text", ""),
                "filename": getter("filename", ""),
                "file_type": getter("file_type", ""),
                "page_number": getter("page_number", 0),
                "chunk_id": getter("chunk_id", ""),
                "parent_chunk_id": getter("parent_chunk_id", ""),
                "root_chunk_id": getter("root_chunk_id", ""),
                "chunk_level": getter("chunk_level", 0),
                "chunk_idx": getter("chunk_idx", 0),
                "pid": getter("pid", ""),
                "score": getter("distance", getter("score", 0.0))
            })
        return formatted

    def delete(self, filter_expr: str):
        return self._get_client().delete(collection_name=self.collection_name, filter=filter_expr)

    def drop_collection(self):
        client = self._get_client()
        if client.has_collection(self.collection_name):
            client.drop_collection(self.collection_name)
