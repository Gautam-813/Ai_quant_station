"""
Full server config backup — SSL certs, nginx, .env, pip freeze → HuggingFace.
Run weekly. Restores the entire server config after a fresh OS install.
"""
import sys
import io
import gzip
import json
import os
import subprocess
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import settings
from huggingface_hub import HfApi, login

HF_REPO = os.getenv("HF_BACKUP_REPO", "TheFinanceEngineer/impulse-analyst-backups")

def _run(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""

def gather_configs() -> dict[str, bytes]:
    """Collect all server config files into a dict of {path: content}."""
    files = {}

    # .env file
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        files["env/.env"] = env_path.read_bytes()

    # nginx config
    nginx_conf = Path("/etc/nginx/sites-available/thefinanceengine.com")
    if nginx_conf.exists():
        files["nginx/thefinanceengine.com"] = nginx_conf.read_bytes()

    nginx_main = Path("/etc/nginx/nginx.conf")
    if nginx_main.exists():
        files["nginx/nginx.conf"] = nginx_main.read_bytes()

    # SSL certs (letsencrypt archive)
    ssl_dir = Path("/etc/letsencrypt/live")
    if ssl_dir.exists():
        for domain_dir in ssl_dir.iterdir():
            if domain_dir.is_dir():
                for cert_file in domain_dir.iterdir():
                    rel = f"letsencrypt/live/{domain_dir.name}/{cert_file.name}"
                    if cert_file.is_file() and not cert_file.name.endswith(".pem"):
                        continue
                    files[rel] = cert_file.read_bytes()

    # systemd service
    svc = Path("/etc/systemd/system/impulse-analyst.service")
    if svc.exists():
        files["systemd/impulse-analyst.service"] = svc.read_bytes()

    # pip freeze
    pip_freeze = _run([sys.executable, "-m", "pip", "freeze", "--local"])
    if pip_freeze:
        files["python/pip_freeze.txt"] = pip_freeze.encode()

    # Project info
    project_root = Path(__file__).resolve().parent.parent.parent
    git_commit = _run(["git", "-C", str(project_root), "rev-parse", "HEAD"])
    if git_commit:
        files["project/git_commit.txt"] = git_commit.encode()

    backup_info = {
        "timestamp": datetime.utcnow().isoformat(),
        "hostname": _run(["hostname"]),
        "files": list(files.keys()),
    }
    files["backup_meta.json"] = json.dumps(backup_info, indent=2).encode()

    return files

def create_bundle(files: dict[str, bytes]) -> bytes:
    """Create a gzipped tar archive from the file dict."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path, content in files.items():
            info = tarfile.TarInfo(name=path)
            info.size = len(content)
            info.mtime = int(datetime.utcnow().timestamp())
            tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()

def upload_bundle(data: bytes, filename: str):
    token = settings.HUGGINGFACE_API_KEY
    if not token:
        print("[FULLBACKUP] No HUGGINGFACE_API_KEY, skipping upload")
        return False
    login(token=token)
    api = HfApi()
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as f:
        f.write(data)
        tmp = f.name
    try:
        api.upload_file(path_or_fileobj=tmp, path_in_repo=filename, repo_id=HF_REPO, repo_type="dataset")
        print(f"[FULLBACKUP] Uploaded {filename} ({len(data)} bytes)")
        return True
    finally:
        os.unlink(tmp)

def main():
    print("[FULLBACKUP] Gathering server configs...")
    files = gather_configs()
    print(f"[FULLBACKUP] Collected {len(files)} files")

    bundle = create_bundle(files)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"server_config_{ts}.tar.gz"

    ok = upload_bundle(bundle, filename)
    if ok:
        print(f"[FULLBACKUP] Done — stored as {filename}")
    else:
        print("[FULLBACKUP] Skipped (no HF token)")

if __name__ == "__main__":
    main()
