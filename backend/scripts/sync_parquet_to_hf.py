"""
Syncs local parquet files to HuggingFace after each MT5 data sync.
Uploads current-year files (which get updated daily).
Run after mt5 sync completes.
"""
import sys
import logging
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import settings
from app.core.historical_loader import LOCAL_CACHE, HF_REPO_ID
from huggingface_hub import HfApi, login

logger = logging.getLogger(__name__)

def sync_parquet_to_hf():
    token = settings.HUGGINGFACE_API_KEY
    if not token:
        logger.warning("No HUGGINGFACE_API_KEY configured, skipping parquet upload")
        return False

    login(token=token)
    api = HfApi()
    current_year = datetime.now().year
    parquet_dir = Path(LOCAL_CACHE)

    if not parquet_dir.exists():
        logger.warning(f"Parquet cache directory not found: {parquet_dir}")
        return False

    files = list(parquet_dir.glob(f"*_{current_year}.parquet"))
    if not files:
        logger.info(f"No {current_year} parquet files found to upload")
        return False

    logger.info(f"Found {len(files)} current-year parquet files to sync to HF")

    for fpath in files:
        remote_path = f"data/{fpath.name}"
        try:
            api.upload_file(
                path_or_fileobj=str(fpath),
                path_in_repo=remote_path,
                repo_id=HF_REPO_ID,
                repo_type="dataset",
            )
            logger.info(f"  Uploaded {fpath.name} -> {HF_REPO_ID}/{remote_path}")
        except Exception as e:
            logger.error(f"  Failed to upload {fpath.name}: {e}")

    logger.info("Parquet sync to HuggingFace complete")
    return True

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
    sync_parquet_to_hf()
