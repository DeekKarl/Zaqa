from fastapi import APIRouter, FastAPI, File, UploadFile, HTTPException

from services.extraction_service import process_file, UnsupportedFileType
from schema.models import Item, ExtractionResult

router = APIRouter()
app=FastAPI()
@router.post(
    "/extract_order2",
    response_model=ExtractionResult,
    responses={400: {"description": "No items detected"}, 415: {"description": "Unsupported file type"}}
)
async def extract_order(file: UploadFile = File(...)):
    data = await file.read()
    try:
        items: list[Item] = process_file(data, file.content_type, file.filename)
    except UnsupportedFileType as e:
        raise HTTPException(status_code=415, detail=str(e))

    if not items:
        raise HTTPException(status_code=400, detail="No order items detected")

    summary = "\n".join(f"{it.quantity} × {it.name}" for it in items)
    return ExtractionResult(items=items, summary=summary)
