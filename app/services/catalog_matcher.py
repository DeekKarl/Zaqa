from typing import List, Dict
from fastapi import APIRouter, HTTPException
import asyncpg
from openai import OpenAI
from rapidfuzz import process

router = APIRouter()
openai_client = OpenAI()

dsn = "postgresql://user:pass@db:5432/zaqa"

@router.on_event("startup")
async def startup():
    router.state.pool = await asyncpg.create_pool(dsn=dsn)

@router.post("/skus")
async def match_skus(payload: Dict[str, List[str]]):
    if "skus" not in payload:
        raise HTTPException(400, "No skus key supplied")
    pool = router.state.pool
    results = []
    async with pool.acquire() as conn:
        for raw in payload["skus"]:
            row = await conn.fetchrow("SELECT * FROM catalog WHERE sku=$1", raw)
            if row:
                results.append({"extracted": raw, "matches": [{"sku": row['sku'], "confidence": 1.0}]})
                continue
            emb = (await openai_client.embeddings.create(input=raw, model="text-embedding-3-small")).data[0].embedding
            candidates = await conn.fetch(
                "SELECT sku, name, embedding <-> $1 AS dist FROM catalog ORDER BY embedding <-> $1 LIMIT 5",
                emb, 5
            )
            names = [c['name'] for c in candidates]
            best, score, idx = process.extractOne(raw, names)
            top = candidates[idx]
            conf = round(1 - top['dist'], 3)
            matches = [{"sku": top['sku'], "confidence": conf}]
            for i, c in enumerate(candidates):
                if i != idx:
                    matches.append({"sku": c['sku'], "confidence": round(1 - c['dist'], 3)})
            results.append({"extracted": raw, "matches": matches})
    return {"matches": results}