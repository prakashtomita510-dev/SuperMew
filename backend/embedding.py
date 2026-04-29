"""文本向量化服务 - 支持密集向量和稀疏向量（BM25）"""
import os
import re
import math
import json
import time
import random
import requests
from collections import Counter
from dotenv import load_dotenv

load_dotenv()


class EmbeddingService:
    """文本向量化服务 - 支持密集向量和稀疏向量"""

    _cohere_next_request_ts = 0.0
    _google_next_request_ts = 0.0

    def __init__(self):
        # Support independent API configuration for embedding service
        self.base_url = os.getenv("EMBEDDING_BASE_URL") or os.getenv("BASE_URL")
        self.api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("ARK_API_KEY")
        self.embedder = (
            os.getenv("EMBEDDER")
            or os.getenv("EMBEDDING_MODEL")
            or "embedding-3-pro"
        )
        self.session = requests.Session()
        self.max_retries = int(os.getenv("EMBEDDING_MAX_RETRIES", "8"))
        self.default_backoff_seconds = float(os.getenv("EMBEDDING_BACKOFF_BASE_SECONDS", "5"))
        self.max_backoff_seconds = float(os.getenv("EMBEDDING_MAX_BACKOFF_SECONDS", "300"))
        self.request_timeout_seconds = int(os.getenv("EMBEDDING_REQUEST_TIMEOUT_SECONDS", "60"))
        # Be conservative for evaluation runs: serialize Cohere calls and leave headroom under the documented limit.
        self.cohere_batch_limit = int(os.getenv("COHERE_EMBED_BATCH_LIMIT", "32"))
        self.cohere_min_interval_seconds = float(os.getenv("COHERE_EMBED_MIN_INTERVAL_SECONDS", "5"))
        self.google_batch_limit = int(os.getenv("GOOGLE_EMBED_BATCH_LIMIT", "32"))
        self.google_min_interval_seconds = float(os.getenv("GOOGLE_EMBED_MIN_INTERVAL_SECONDS", "3"))
        
        # BM25 参数
        self.k1 = 1.5  # 词频饱和参数
        self.b = 0.75  # 文档长度归一化参数
        
        # 持久化文件
        self.metadata_file = os.path.join(os.path.dirname(__file__), "bm25_metadata.json")
        
        # 词汇表
        self._vocab = {}
        self._vocab_counter = 0
        
        # 文档频率统计
        self._doc_freq = Counter()
        self._total_docs = 0
        self._avg_doc_len = 0
        self._state_mtime = None
        
        self.load_state()

    def load_state(self):
        """从文件加载 BM25 状态"""
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._vocab = data.get("vocab", {})
                    self._vocab_counter = data.get("vocab_counter", 0)
                    self._doc_freq = Counter(data.get("doc_freq", {}))
                    self._total_docs = data.get("total_docs", 0)
                    self._avg_doc_len = data.get("avg_doc_len", 0)
                    self._state_mtime = os.path.getmtime(self.metadata_file)
            except Exception as e:
                print(f"⚠️ 加载 BM25 状态失败: {e}")

    def save_state(self):
        """将 BM25 状态保存到文件"""
        try:
            data = {
                "vocab": self._vocab,
                "vocab_counter": self._vocab_counter,
                "doc_freq": dict(self._doc_freq),
                "total_docs": self._total_docs,
                "avg_doc_len": self._avg_doc_len
            }
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            self._state_mtime = os.path.getmtime(self.metadata_file)
        except Exception as e:
            print(f"⚠️ 保存 BM25 状态失败: {e}")

    def refresh_state_if_needed(self):
        """在其他进程/模块更新 BM25 状态后按需刷新本实例。"""
        if not os.path.exists(self.metadata_file):
            return
        try:
            current_mtime = os.path.getmtime(self.metadata_file)
        except OSError:
            return
        if self._state_mtime is None or current_mtime > self._state_mtime:
            self.load_state()

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        调用嵌入 API 生成密集向量（支持 Cohere v2 和 OpenAI 兼容格式）
        :param texts: 待转换的文本列表（支持批量）
        :return: 向量列表
        """
        is_cohere = "cohere" in (self.base_url or "").lower()
        is_google = self._is_google_embedding_backend()

        if is_google:
            return self._get_google_embeddings(texts)

        headers = {"Content-Type": "application/json"}

        if is_cohere:
            headers["Authorization"] = f"Bearer {self.api_key}"
            # Cohere v2 API structure
            endpoint = f"{self.base_url}/embed"
            data = {
                "model": self.embedder,
                "texts": texts,
                "input_type": "search_document",
                "embedding_types": ["float"],
            }
        else:
            # OpenAI-compatible API structure
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            endpoint = f"{self.base_url}/embeddings"
            data = {
                "model": self.embedder,
                "input": texts,
                "encoding_format": "float"
            }

        if is_cohere and len(texts) > self.cohere_batch_limit:
            combined = []
            for start in range(0, len(texts), self.cohere_batch_limit):
                batch = texts[start:start + self.cohere_batch_limit]
                combined.extend(self.get_embeddings(batch))
            return combined

        for attempt in range(self.max_retries):
            try:
                if is_cohere:
                    self._wait_for_cohere_slot()

                response = self.session.post(
                    endpoint,
                    headers=headers,
                    json=data,
                    timeout=self.request_timeout_seconds,
                )
                
                if response.status_code == 429:
                    wait_time = self._retry_wait_seconds(response, attempt)
                    print(f"⚠️ 429 Too Many Requests, 重试中 ({attempt + 1}/{self.max_retries})，等待 {wait_time:.2f}s...")
                    time.sleep(wait_time)
                    continue
                
                if response.status_code >= 500:
                    wait_time = self._retry_wait_seconds(response, attempt)
                    print(f"⚠️ 服务器错误 {response.status_code}, 重试中 ({attempt + 1}/{self.max_retries})，等待 {wait_time:.2f}s...")
                    time.sleep(wait_time)
                    continue

                if response.status_code >= 400:
                    response.raise_for_status()
                result = response.json()

                if is_cohere:
                    # Cohere v2 response: {"embeddings": {"float": [[...], ...]}}
                    return result["embeddings"]["float"]
                else:
                    # OpenAI-compatible response: {"data": [{"embedding": [...]}]}
                    return [item["embedding"] for item in result["data"]]
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response is not None else None
                if status_code is not None and 400 <= status_code < 500 and status_code != 429:
                    raise Exception(f"嵌入 API 返回不可重试错误 {status_code}: {e.response.text}") from e
                if attempt == self.max_retries - 1:
                    raise Exception(f"嵌入 API 调用在 {self.max_retries} 次重试后失败: {str(e)}")
                wait_time = self._retry_wait_seconds(e.response, attempt)
                print(f"⚠️ 网络或其它错误: {str(e)}, 重试中 ({attempt + 1}/{self.max_retries})，等待 {wait_time:.2f}s...")
                time.sleep(wait_time)
            except (requests.exceptions.RequestException, Exception) as e:
                if attempt == self.max_retries - 1:
                    raise Exception(f"嵌入 API 调用在 {self.max_retries} 次重试后失败: {str(e)}")
                
                wait_time = self._retry_wait_seconds(None, attempt)
                print(f"⚠️ 网络或其它错误: {str(e)}, 重试中 ({attempt + 1}/{self.max_retries})，等待 {wait_time:.2f}s...")
                time.sleep(wait_time)
        
        # If we exit the loop without returning, it means we exhausted retries on 429/500 without triggering the exception block
        raise Exception(f"嵌入 API 调用在 {self.max_retries} 次重试后失败（由于持续的频率限制或服务器错误）。")

    def _is_google_embedding_backend(self) -> bool:
        return "generativelanguage.googleapis.com" in (self.base_url or "").lower()

    def _normalize_google_base_url(self) -> str:
        base = (self.base_url or "").rstrip("/")
        if base.endswith("/openai"):
            base = base[:-7]
        return base

    def _google_model_name(self) -> str:
        model = self.embedder.strip()
        return model if model.startswith("models/") else f"models/{model}"

    def get_output_dim(self) -> int:
        explicit_dim = os.getenv("EMBEDDING_DIMENSION") or os.getenv("EMBEDDING_OUTPUT_DIM")
        if explicit_dim:
            return int(str(explicit_dim).strip().strip('"').strip("'"))

        model = self.embedder.strip().lower()
        if model.endswith("text-embedding-004"):
            return 768
        if model.endswith("gemini-embedding-001"):
            return int(os.getenv("GOOGLE_EMBED_OUTPUT_DIM", "3072"))
        if model.endswith("gemini-embedding-2-preview"):
            return int(os.getenv("GOOGLE_EMBED_OUTPUT_DIM", "3072"))
        return int(os.getenv("EMBEDDING_OUTPUT_DIM", "1536"))

    def _get_google_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if len(texts) > self.google_batch_limit:
            combined = []
            for start in range(0, len(texts), self.google_batch_limit):
                batch = texts[start:start + self.google_batch_limit]
                combined.extend(self._get_google_embeddings(batch))
            return combined

        endpoint = f"{self._normalize_google_base_url()}/{self._google_model_name()}:batchEmbedContents"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        requests_payload = []
        for text in texts:
            requests_payload.append(
                {
                    "model": self._google_model_name(),
                    "content": {"parts": [{"text": text}]},
                }
            )

        payload = {"requests": requests_payload}

        for attempt in range(self.max_retries):
            try:
                self._wait_for_google_slot()
                response = self.session.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self.request_timeout_seconds,
                )
                if response.status_code == 429:
                    wait_time = self._retry_wait_seconds(response, attempt)
                    print(f"⚠️ 429 Too Many Requests, 重试中 ({attempt + 1}/{self.max_retries})，等待 {wait_time:.2f}s...")
                    time.sleep(wait_time)
                    continue
                if response.status_code >= 500:
                    wait_time = self._retry_wait_seconds(response, attempt)
                    print(f"⚠️ 服务器错误 {response.status_code}, 重试中 ({attempt + 1}/{self.max_retries})，等待 {wait_time:.2f}s...")
                    time.sleep(wait_time)
                    continue
                if response.status_code >= 400:
                    response.raise_for_status()

                result = response.json()
                return [item["values"] for item in result.get("embeddings", [])]
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response is not None else None
                if status_code is not None and 400 <= status_code < 500 and status_code != 429:
                    raise Exception(f"Google embedding 返回不可重试错误 {status_code}: {e.response.text}") from e
                if attempt == self.max_retries - 1:
                    raise Exception(f"Google embedding 在 {self.max_retries} 次重试后失败: {str(e)}")
                wait_time = self._retry_wait_seconds(e.response, attempt)
                print(f"⚠️ Google embedding 错误: {str(e)}, 重试中 ({attempt + 1}/{self.max_retries})，等待 {wait_time:.2f}s...")
                time.sleep(wait_time)
            except (requests.exceptions.RequestException, Exception) as e:
                if attempt == self.max_retries - 1:
                    raise Exception(f"Google embedding 在 {self.max_retries} 次重试后失败: {str(e)}")
                wait_time = self._retry_wait_seconds(None, attempt)
                print(f"⚠️ Google embedding 错误: {str(e)}, 重试中 ({attempt + 1}/{self.max_retries})，等待 {wait_time:.2f}s...")
                time.sleep(wait_time)

        raise Exception(f"Google embedding 在 {self.max_retries} 次重试后失败（由于持续的频率限制或服务器错误）。")

    def _wait_for_cohere_slot(self):
        now = time.monotonic()
        wait_seconds = EmbeddingService._cohere_next_request_ts - now
        if wait_seconds > 0:
            print(f"⏳ Cohere 节流等待 {wait_seconds:.2f}s...")
            time.sleep(wait_seconds)
        EmbeddingService._cohere_next_request_ts = time.monotonic() + self.cohere_min_interval_seconds

    def _wait_for_google_slot(self):
        now = time.monotonic()
        wait_seconds = EmbeddingService._google_next_request_ts - now
        if wait_seconds > 0:
            print(f"⏳ Google embedding 节流等待 {wait_seconds:.2f}s...")
            time.sleep(wait_seconds)
        EmbeddingService._google_next_request_ts = time.monotonic() + self.google_min_interval_seconds

    def _retry_wait_seconds(self, response: requests.Response | None, attempt: int) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(float(retry_after), self.max_backoff_seconds)
                except ValueError:
                    pass
        backoff = self.default_backoff_seconds * (2 ** attempt)
        backoff = min(backoff, self.max_backoff_seconds)
        return backoff + random.random()

    def tokenize(self, text: str) -> list[str]:
        """
        简单分词器 - 支持中英文混合
        :param text: 输入文本
        :return: 分词结果
        """
        # 中文按字符分割，英文按空格和标点分割
        # 移除标点和特殊字符
        text = text.lower()
        
        tokens = []
        # 匹配中文字符
        chinese_pattern = re.compile(r'[\u4e00-\u9fff]')
        # 匹配英文单词
        english_pattern = re.compile(r'[a-zA-Z]+')
        
        i = 0
        while i < len(text):
            char = text[i]
            if chinese_pattern.match(char):
                # 中文字符单独作为一个 token
                tokens.append(char)
                i += 1
            elif english_pattern.match(char):
                # 英文单词
                match = english_pattern.match(text[i:])
                if match:
                    tokens.append(match.group())
                    i += len(match.group())
            else:
                i += 1
        
        return tokens

    def fit_corpus(self, texts: list[str]):
        """
        拟合语料库，计算 IDF 和平均文档长度
        :param texts: 文档列表
        """
        self._vocab = {}
        self._vocab_counter = 0
        self._doc_freq = Counter()
        self._total_docs = len(texts)
        total_len = 0
        
        for text in texts:
            tokens = self.tokenize(text)
            total_len += len(tokens)
            
            # 统计文档频率（每个词在多少文档中出现）
            unique_tokens = set(tokens)
            for token in unique_tokens:
                self._doc_freq[token] += 1
                
                # 建立词汇表
                if token not in self._vocab:
                    self._vocab[token] = self._vocab_counter
                    self._vocab_counter += 1
        
        self._avg_doc_len = total_len / self._total_docs if self._total_docs > 0 else 1

    def get_sparse_embedding(self, text: str) -> dict:
        """
        生成 BM25 稀疏向量
        :param text: 输入文本
        :return: 稀疏向量 {index: value, ...}
        """
        self.refresh_state_if_needed()
        tokens = self.tokenize(text)
        doc_len = len(tokens)
        tf = Counter(tokens)
        
        sparse_vector = {}
        
        for token, freq in tf.items():
            if token not in self._vocab:
                # 新词加入词汇表
                self._vocab[token] = self._vocab_counter
                self._vocab_counter += 1
            
            idx = self._vocab[token]
            
            # 计算 IDF
            df = self._doc_freq.get(token, 0)
            if df == 0:
                # 新词，使用平滑 IDF
                idf = math.log((self._total_docs + 1) / 1)
            else:
                idf = math.log((self._total_docs - df + 0.5) / (df + 0.5) + 1)
            
            # 计算 BM25 分数
            numerator = freq * (self.k1 + 1)
            denominator = freq + self.k1 * (1 - self.b + self.b * doc_len / max(self._avg_doc_len, 1))
            score = idf * numerator / denominator
            
            if score > 0:
                sparse_vector[idx] = float(score)
        
        return sparse_vector

    def get_sparse_embeddings(self, texts: list[str]) -> list[dict]:
        """
        批量生成 BM25 稀疏向量
        :param texts: 文本列表
        :return: 稀疏向量列表
        """
        return [self.get_sparse_embedding(text) for text in texts]

    def get_all_embeddings(self, texts: list[str]) -> tuple[list[list[float]], list[dict]]:
        """
        同时生成密集向量和稀疏向量
        :param texts: 文本列表
        :return: (密集向量列表, 稀疏向量列表)
        """
        dense_embeddings = self.get_embeddings(texts)
        sparse_embeddings = self.get_sparse_embeddings(texts)
        return dense_embeddings, sparse_embeddings
