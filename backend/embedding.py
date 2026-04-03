"""文本向量化服务 - 支持密集向量和稀疏向量（BM25）"""
import os
import re
import math
import requests
from collections import Counter
from dotenv import load_dotenv

load_dotenv()


class EmbeddingService:
    """文本向量化服务 - 支持密集向量和稀疏向量"""

    def __init__(self):
        # Support independent API configuration for embedding service
        self.base_url = os.getenv("EMBEDDING_BASE_URL") or os.getenv("BASE_URL")
        self.api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("ARK_API_KEY")
        self.embedder = os.getenv("EMBEDDER", "embedding-3-pro")
        
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
        except Exception as e:
            print(f"⚠️ 保存 BM25 状态失败: {e}")

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        调用嵌入 API 生成密集向量
        :param texts: 待转换的文本列表（支持批量）
        :return: 向量列表
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.embedder,
            "input": texts,
            "encoding_format": "float"
        }

        try:
            response = requests.post(f"{self.base_url}/embeddings", headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            return [item["embedding"] for item in result["data"]]
        except Exception as e:
            raise Exception(f"嵌入 API 调用失败: {str(e)}")

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