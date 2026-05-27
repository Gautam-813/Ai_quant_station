"""
Daily database backup — dumps PostgreSQL to gzip, uploads to HuggingFace.
Usage: python scripts/backup_db.py
Cron:  0 3 * * * cd /opt/impulse_analyst && backend/venv/bin/python backend/scripts/backup_db.py
"""
import os
import sys
import gzip
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import settings
from huggingface_hub import HfApi, login

DB_NAME = os.getenv("DB_NAME", "finance_engine")
DB_USER = os.getenv("DB_USER", "admin_user")
HF_REPO = os.getenv("HF_BACKUP_REPO", "TheFinanceEngineer/impulse-analyst-backups")
RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))

def _run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{r.stderr}")
    return r.stdout.strip()

def dump_db() -> bytes:
    print("[BACKUP] Dumping database...")
    out = _run(["pg_dump", f"--dbname=postgresql://{DB_USER}@{settings.DB_HOST}:{settings.DB_PORT}/{DB_NAME}"])
    compressed = gzip.compress(out.encode())
    print(f"[BACKUP] Dumped {len(out)} chars -> {len(compressed)} bytes gzipped")
    return compressed

def upload_to_hf(data: bytes, filename: str):
    print(f"[BACKUP] Uploading {filename} to HuggingFace...")
    token = settings.HUGGINGFACE_API_KEY
    if not token:
        print("[BACKUP] No HUGGINGFACE_API_KEY configured, skipping upload")
        return False
    login(token=token)
    api = HfApi()
    with tempfile.NamedTemporaryFile(suffix=".sql.gz", delete=False) as f:
        f.write(data)
        tmp = f.name
    try:
        api.upload_file(
            path_or_fileobj=tmp,
            path_in_repo=filename,
            repo_id=HF_REPO,
            repo_type="dataset",
        )
        print(f"[BACKUP] Uploaded successfully")
        return True
    finally:
        os.unlink(tmp)

def clean_old_backups(keep_days: int = RETENTION_DAYS):
    print(f"[BACKUP] Cleaning backups older than {keep_days} days...")
    token = settings.HUGGINGFACE_API_KEY
    if not token:
        return
    login(token=token)
    api = HfApi()
    try:
        files = api.list_repo_files(repo_id=HF_REPO, repo_type="dataset")
        cutoff = datetime.utcnow().timestamp() - keep_days * 86400
        for f in files:
            if not f.startswith("db_"):
                continue
            info = api.get_paths_info(repo_id=HF_REPO, paths=[f], repo_type="dataset")
            if info and info[0].last_commit_date.timestamp() < cutoff:
                api.delete_file(path_in_repo=f, repo_id=HF_REPO, repo_type="dataset")
                print(f"[BACKUP] Deleted old backup: {f}")
    except Exception as e:
        print(f"[BACKUP] Cleanup skipped: {e}")

def main():
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"db_{ts}.sql.gz"
    try:
        data = dump_db()
        ok = upload_to_hf(data, filename)
        if ok:
            clean_old_backups()
        print(f"[BACKUP] Done")
    except Exception as e:
        print(f"[BACKUP] FAILED: {e}")
        raise

if __name__ == "__main__":
    main()
