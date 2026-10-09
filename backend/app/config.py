import os
from pathlib import Path

# Base Paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
UPLOAD_DIR = BACKEND_DIR / "uploads"
PAGES_DIR = UPLOAD_DIR / "pages"
STATIC_DIR = PROJECT_ROOT / "frontend" / "dist"

# Ensure runtime directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PAGES_DIR.mkdir(parents=True, exist_ok=True)

# Database Configuration
DB_PATH = DATA_DIR / "electrical_records.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

# VLM Inference Configuration
# Default target model: Qwen/Qwen2.5-VL-3B-Instruct
VLM_MODEL_ID = os.getenv("VLM_MODEL_ID", "Qwen/Qwen2.5-VL-3B-Instruct")
VLM_DEVICE = os.getenv("VLM_DEVICE", "auto")  # 'auto', 'cuda', 'cpu'
VLM_TORCH_DTYPE = os.getenv("VLM_TORCH_DTYPE", "float16")  # 'float16', 'bfloat16', 'float32'
VLM_MAX_NEW_TOKENS = int(os.getenv("VLM_MAX_NEW_TOKENS", "1536"))

# Rendering Configuration
PDF_RENDER_DPI = int(os.getenv("PDF_RENDER_DPI", "300"))

# Server Configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1")
