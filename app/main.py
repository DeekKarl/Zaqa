from fastapi import FastAPI
from app.services.catalog_matcher import router as matcher_router

app = FastAPI(
    title="Zaqa SKU Matcher",
    version="0.1.0"
)

app.include_router(matcher_router, prefix="/match")

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
