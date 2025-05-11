from typing import List
from pydantic import BaseModel

class Item(BaseModel):
    name: str
    quantity: int

class ExtractionResult(BaseModel):
    items: List[Item]
    summary: str
