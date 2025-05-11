import os
from huggingface_hub import hf_hub_download

token = os.getenv("HF_TOKEN")
if not token:
    raise RuntimeError("Please set HF_TOKEN in your environment before running")

# This will download only the Q4_0 .bin directly into ./models/
out_path = hf_hub_download(
    repo_id="meta-llama/Llama-2-7b",
    filename="llama-2-7b.Q4_0.bin",
    token=token,
    cache_dir="./models",
    library_name="llama.cpp"
)

print("Downloaded model to:", out_path)
