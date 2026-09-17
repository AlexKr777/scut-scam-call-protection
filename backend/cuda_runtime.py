"""Make NVIDIA pip runtime DLLs visible to CTranslate2 on Windows."""
from __future__ import annotations

import os
from pathlib import Path


def configure_cuda_dll_path() -> list[str]:
    """Prepend installed CUDA 12 runtime directories before importing CTranslate2."""
    if os.name != "nt":
        return []

    directories: list[str] = []
    try:
        import nvidia.cublas
        import nvidia.cuda_nvrtc
        import nvidia.cudnn

        for package in (nvidia.cudnn, nvidia.cublas, nvidia.cuda_nvrtc):
            directory = Path(next(iter(package.__path__))) / "bin"
            if directory.is_dir():
                directories.append(str(directory))
    except (ImportError, StopIteration):
        return []

    if directories:
        existing = os.environ.get("PATH", "")
        existing_directories = {item.casefold() for item in existing.split(os.pathsep) if item}
        missing = [directory for directory in directories if directory.casefold() not in existing_directories]
        if missing:
            os.environ["PATH"] = os.pathsep.join([*missing, existing])
    return directories
