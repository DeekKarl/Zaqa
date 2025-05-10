import csv
import asyncpg
from openai import OpenAI

async def seed():
    pool = await asyncpg.create_pool(dsn="postgresql://user:pass@db:5432/zaqa")
    client = OpenAI()
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS catalog (
                sku text PRIMARY KEY,
                name text,
                description text,
                embedding vector(1536)
            );"""
        )
        with open('catalog.csv') as f:
            reader = csv.DictReader(f)
            for row in reader:
                text = f"SKU: {row['sku']} | Name: {row['name']} | Desc: {row['description']}"
                emb = (await client.embeddings.create(input=text, model="text-embedding-3-small")).data[0].embedding
                await conn.execute(
                    "INSERT INTO catalog (sku, name, description, embedding) VALUES ($1,$2,$3,$4) ON CONFLICT (sku) DO NOTHING;",
                    row['sku'], row['name'], row['description'], emb
                )

if __name__ == '__main__':
    import asyncio; asyncio.run(seed())
