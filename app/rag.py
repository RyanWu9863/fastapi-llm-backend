import asyncio
import re

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings
from app.schemas import Source

# 中文約 400 字一塊：太大會混進不相關內容、稀釋檢索精準度；太小又會失去上下文
CHUNK_SIZE = 400
# 硬切時相鄰兩塊重疊 80 字，避免關鍵句剛好被切在交界而兩邊都不完整
CHUNK_OVERLAP = 80

_client = chromadb.PersistentClient(
    path=settings.chroma_path, settings=ChromaSettings(anonymized_telemetry=False)
)
# embedding_function=None：向量由我們用 Ollama 算好再傳進來，不讓 Chroma 另外下載模型
# cosine：比較向量的「方向」而不是長度，是文字相似度最常用的算法
_collection = _client.get_or_create_collection(
    "documents", embedding_function=None, configuration={"hnsw": {"space": "cosine"}}
)


def split_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Markdown 先按標題切成章節，一個章節盡量放同一塊；章節太長再按段落切。

    純文字檔沒有標題，就整份當成一個章節處理。
    """
    # 在每個標題行前面切開，讓標題跟它底下的內容留在同一塊
    sections = [
        s.strip() for s in re.split(r"\n(?=#{1,6} )", text.replace("\r\n", "\n")) if s.strip()
    ]
    chunks: list[str] = []
    prefix = ""
    for section in sections:
        if "\n" not in section and section.startswith("#"):
            # 只有標題、沒有內容（例如文件大標題）：併進下一個章節
            prefix += section + "\n"
            continue
        section, prefix = prefix + section, ""
        heading = section.split("\n", 1)[0] if section.startswith("#") else ""
        parts = _split_paragraphs(section, chunk_size, overlap)
        # 章節被切成多塊時，後面幾塊補上章節標題，檢索時才看得出這段在講什麼
        chunks += [parts[0]] + [f"{heading}\n{p}" if heading else p for p in parts[1:]]
    if prefix:
        chunks.append(prefix.strip())
    return chunks


def _split_paragraphs(text: str, chunk_size: int, overlap: int) -> list[str]:
    """把相鄰的短段落合併到接近 chunk_size；單一段落太長才硬切，相鄰塊重疊 overlap 字。"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for p in paragraphs:
        if current and len(current) + 1 + len(p) <= chunk_size:
            current += "\n" + p
            continue
        if current:
            chunks.append(current)
        while len(p) > chunk_size:
            chunks.append(p[:chunk_size])
            p = p[chunk_size - overlap :]
        current = p
    if current:
        chunks.append(current)
    return chunks


# Chroma 的 API 是同步的：用 asyncio.to_thread 丟到 thread 執行，避免卡住 event loop


async def add_document(
    document_id: str, filename: str, chunks: list[str], embeddings: list[list[float]]
) -> None:
    await asyncio.to_thread(
        _collection.add,
        ids=[f"{document_id}:{i}" for i in range(len(chunks))],
        embeddings=embeddings,
        documents=chunks,
        metadatas=[
            {"document_id": document_id, "filename": filename, "chunk_index": i}
            for i in range(len(chunks))
        ],
    )


async def search(query_embedding: list[float], top_k: int) -> list[Source]:
    """回傳最相關的 top_k 個片段，依距離由近到遠排序。"""
    r = await asyncio.to_thread(
        _collection.query,
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    # query 可以一次查多個向量，所以結果都多包一層 list；我們只查一個，取 [0]
    return [
        Source(**meta, text=doc, distance=dist)
        for doc, meta, dist in zip(r["documents"][0], r["metadatas"][0], r["distances"][0])
    ]
