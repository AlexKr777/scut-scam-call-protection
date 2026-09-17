from pathlib import Path
from huggingface_hub import snapshot_download

root=Path(__file__).resolve().parents[1]/".local"/"models"/"mdeberta-v3-base-mnli-xnli"
snapshot_download("MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",local_dir=str(root),allow_patterns=["config.json","tokenizer.json","tokenizer_config.json","special_tokens_map.json","spm.model","onnx/model_quantized.onnx"])
source=root/"onnx"/"model_quantized.onnx"; target=root/"model_quantized.onnx"
if source.exists() and not target.exists(): source.replace(target)
print(root)
