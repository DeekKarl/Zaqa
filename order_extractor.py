import io
import re
import csv
import logging
import tempfile
from typing import List, Dict, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException
from pdf2image import convert_from_bytes
from PIL import Image
import pytesseract
from word2number import w2n
import inflect

from invoice2data import extract_data as invoice_extract

app = FastAPI()
logging.basicConfig(level=logging.INFO)
inflector = inflect.engine()

def ocr_image(image: Image.Image) -> str:
    return pytesseract.image_to_string(image)

def to_int(token: str) -> Optional[int]:
    try:
        return int(token)
    except ValueError:
        try:
            return w2n.word_to_num(token)
        except Exception:
            return None

def singularize(word: str) -> str:
    return inflector.singular_noun(word) or word

def split_phrases(desc: str) -> List[str]:
    return re.split(r'\band\b|,|;', desc, flags=re.IGNORECASE)

def parse_segment(
    raw_qty: str,
    rest: str,
    default_noun: Optional[str] = None
) -> List[Dict[str,int]]:
    qty0 = to_int(raw_qty)
    if qty0 is None:
        return []
    rest = rest.strip()
    if not rest:
        return []

    # pattern 1: "2 x Widget A"
    m1 = re.match(r'^(?:x|×)\s*(.+)$', rest, re.IGNORECASE)
    if m1:
        return [{"name": m1.group(1).strip(), "quantity": qty0}]

    # pattern 2: "Widget A: 2"
    m2 = re.match(r'^(?P<name>.+?):\s*(?P<q>\d+)$', rest)
    if m2:
        return [{"name": m2.group("name").strip(), "quantity": int(m2.group("q"))}]

    # noun + descriptors
    parts = rest.split(None, 1)
    if len(parts) > 1:
        entity     = parts[0]
        singular_n = singularize(entity)
        desc_block = parts[1]
    else:
        entity     = default_noun or parts[0]
        singular_n = singularize(entity)
        desc_block = ""

    # if no descriptors at all
    if not desc_block:
        return [{"name": singular_n, "quantity": qty0}]

    subs = split_phrases(desc_block)

    # single-phrase: "<noun> <desc>"
    if len(subs) == 1:
        phr = subs[0].strip()
        m3  = re.match(r'^(?P<num>\d+|\w+)\s+(?P<d>.+)$', phr)
        if m3 and to_int(m3.group("num")) is not None:
            qty      = to_int(m3.group("num")) or qty0
            phr_desc = m3.group("d")
        else:
            qty      = qty0
            phr_desc = phr
        name = f"{singular_n} {phr_desc}".strip()
        return [{"name": name, "quantity": qty}]

    # multi-phrase: each "<desc> <noun>"
    items: List[Dict[str,int]] = []
    for phr in subs:
        phr = phr.strip()
        if not phr:
            continue
        # drop leading entity words
        tok2 = phr.split(None, 1)
        if tok2[0].lower() in (entity.lower(), singular_n.lower()):
            phr = tok2[1] if len(tok2) > 1 else ""
        if not phr:
            continue

        m4 = re.match(r'^(?P<n>\d+)\s+(?P<d>.+)$', phr)
        if m4:
            qty, desc = int(m4.group("n")), m4.group("d")
        else:
            parts2 = phr.split(None, 1)
            num    = to_int(parts2[0])
            if num is not None and len(parts2) > 1:
                qty, desc = num, parts2[1]
            else:
                qty, desc = 1, phr

        name = f"{desc.strip()} {singular_n}".strip()
        items.append({"name": name, "quantity": qty})

    return items


def extract_items_from_text(text: str) -> List[Dict[str,int]]:
    # trim off preamble
    marker = "order the following items"
    low    = text.lower()
    idx    = low.find(marker)
    if idx != -1:
        text = text[idx + len(marker):]

    flat   = re.sub(r'\s+', ' ', text).strip()
    tokens = flat.split(' ')
    items: List[Dict[str,int]] = []
    last_noun: Optional[str] = None
    i = 0

    while i < len(tokens):
        # only break on pure digits
        if not tokens[i].isdigit():
            i += 1
            continue

        qty = int(tokens[i])
        j   = i + 1
        desc_tokens: List[str] = []

        # allow digits if they follow "and"
        while j < len(tokens) and (not tokens[j].isdigit() or tokens[j-1].lower() == "and"):
            desc_tokens.append(tokens[j])
            j += 1

        rest = ' '.join(desc_tokens)
        segment_items = parse_segment(str(qty), rest, last_noun)
        items.extend(segment_items)

        if segment_items:
            # update last noun to the noun of the first parsed item
            last_noun = segment_items[0]["name"].split()[-1]

        i = j

    return items


def extract_items_from_csv(data: bytes) -> List[Dict[str,int]]:
    decoded = data.decode('utf-8', errors='ignore')
    lines: List[str] = []
    for row in csv.reader(decoded.splitlines()):
        if row:
            lines.append(" ".join(row))
    return extract_items_from_text("\n".join(lines))

@app.post("/extract_order")
async def extract_order(file: UploadFile = File(...)):
    data: bytes = await file.read()
    items: List[Dict[str,int]]

    if file.content_type == "application/pdf":
        # try invoice2data first
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            tmp.write(data)
            tmp.flush()
            inv = invoice_extract(tmp.name)

        if inv and inv.get("line_items"):
            items = [
                {
                    "name": li.get("description","").strip(),
                    "quantity": li.get("quantity",1)
                }
                for li in inv["line_items"]
            ]
        else:
            images   = convert_from_bytes(data)
            full_txt = "\n".join(ocr_image(img) for img in images)
            items    = extract_items_from_text(full_txt)

    elif file.content_type.startswith("image/"):
        img      = Image.open(io.BytesIO(data))
        full_txt = ocr_image(img)
        items    = extract_items_from_text(full_txt)

    elif file.content_type in ("text/csv","application/csv") or file.filename.lower().endswith(".csv"):
        items = extract_items_from_csv(data)

    else:
        raise HTTPException(400, "Unsupported file type")

    if not items:
        return {"message": "No order items detected"}

    summary = "\n".join(f"{it['quantity']} × {it['name']}" for it in items)
    return {"items": items, "summary": summary}
