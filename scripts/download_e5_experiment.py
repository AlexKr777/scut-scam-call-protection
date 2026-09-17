"""One-time free local download for the isolated supervised experiment."""
from pathlib import Path
from huggingface_hub import snapshot_download

root = Path(__file__).resolve().parents[1] / ".local" / "models" / "multilingual-e5-base"
print(snapshot_download("intfloat/multilingual-e5-base", local_dir=str(root),
    allow_patterns=["config.json", "tokenizer.json", "tokenizer_config.json",
                    "special_tokens_map.json", "sentencepiece.bpe.model", "model.safetensors"]))
