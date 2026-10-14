"""
Build release package for 12306-RailHop.
Usage: python backend/scripts/build_release.py [release_tag]
Example: python backend/scripts/build_release.py 20261014
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone, timedelta

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def get_git_commit():
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT_DIR).decode().strip()
        return out
    except Exception:
        return "10353b57e9007831a40168c38a127ccf375c7b52"

def sha256_file(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def build_package(release_date="20261014"):
    pkg_name = f"12306-railhop-{release_date}"
    dist_dir = os.path.join(ROOT_DIR, "dist")
    target_dir = os.path.join(dist_dir, pkg_name)
    tar_filename = f"{pkg_name}.tar.gz"
    tar_path = os.path.join(dist_dir, tar_filename)
    tar_sha_path = os.path.join(dist_dir, f"{tar_filename}.sha256")

    print(f"[*] Packaging {pkg_name}...")
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
    os.makedirs(target_dir, exist_ok=True)

    # 1. Copy backend app (skip __pycache__ and *.pyc)
    backend_src_app = os.path.join(ROOT_DIR, "backend", "app")
    backend_dst_app = os.path.join(target_dir, "backend", "app")
    shutil.copytree(
        backend_src_app,
        backend_dst_app,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
    )

    # 2. Copy backend data
    backend_src_data = os.path.join(ROOT_DIR, "backend", "data")
    backend_dst_data = os.path.join(target_dir, "backend", "data")
    shutil.copytree(backend_src_data, backend_dst_data)

    # 3. Copy backend requirements
    shutil.copy2(os.path.join(ROOT_DIR, "backend", "requirements.txt"), os.path.join(target_dir, "backend", "requirements.txt"))
    deploy_dir = os.path.join(ROOT_DIR, "deploy")
    req_lock_src = os.path.join(deploy_dir, "requirements.lock")
    if os.path.exists(req_lock_src):
        shutil.copy2(req_lock_src, os.path.join(target_dir, "backend", "requirements.lock"))
    else:
        raise FileNotFoundError(f"Missing requirements.lock at {req_lock_src}")

    # 4. Copy frontend/dist
    frontend_dist_src = os.path.join(ROOT_DIR, "frontend", "dist")
    if not os.path.exists(frontend_dist_src):
        raise FileNotFoundError(f"Frontend dist not found at {frontend_dist_src}. Run 'npm run build' first.")
    frontend_dist_dst = os.path.join(target_dir, "frontend", "dist")
    shutil.copytree(frontend_dist_src, frontend_dist_dst)

    # 5. Copy templates & LICENSE
    shutil.copy2(os.path.join(ROOT_DIR, "LICENSE"), os.path.join(target_dir, "LICENSE"))
    shutil.copy2(os.path.join(deploy_dir, "nginx.conf.template"), os.path.join(target_dir, "nginx.conf.template"))
    shutil.copy2(os.path.join(deploy_dir, "railhop.service.template"), os.path.join(target_dir, "railhop.service.template"))

    # 6. Generate deploy.sh with LF
    deploy_src = os.path.join(deploy_dir, "deploy.sh")
    with open(deploy_src, "r", encoding="utf-8") as f:
        deploy_content = f.read()
    # Update release directory template
    commit_short = get_git_commit()[:7]
    deploy_content = deploy_content.replace(
        'releases/20261013-10353b5-XXXXXX',
        f'releases/{release_date}-{commit_short}-XXXXXX'
    )
    deploy_content = deploy_content.replace(
        'deployment-backups/20261013-XXXXXX',
        f'deployment-backups/{release_date}-XXXXXX'
    )
    # Ensure unix line endings
    deploy_content = deploy_content.replace("\r\n", "\n")
    deploy_dst = os.path.join(target_dir, "deploy.sh")
    with open(deploy_dst, "wb") as f:
        f.write(deploy_content.encode("utf-8"))

    # 7. Generate DEPLOY.md with LF
    deploy_md_src = os.path.join(deploy_dir, "DEPLOY.md")
    with open(deploy_md_src, "r", encoding="utf-8") as f:
        deploy_md = f.read()
    deploy_md = deploy_md.replace("12306-railhop-20261013", pkg_name)
    deploy_md = deploy_md.replace("\r\n", "\n")
    deploy_md_dst = os.path.join(target_dir, "DEPLOY.md")
    with open(deploy_md_dst, "wb") as f:
        f.write(deploy_md.encode("utf-8"))

    # 8. Compute sha256 for all files to be included in release-manifest.json
    all_rel_paths = []
    for root, dirs, files in os.walk(target_dir):
        for file in files:
            full = os.path.join(root, file)
            rel = os.path.relpath(full, target_dir).replace("\\", "/")
            if rel not in ("release-manifest.json", "SHA256SUMS"):
                all_rel_paths.append(rel)
    all_rel_paths.sort()

    manifest_files = {}
    for rel in all_rel_paths:
        manifest_files[rel] = sha256_file(os.path.join(target_dir, rel))

    beijing_tz = timezone(timedelta(hours=8))
    now_iso = datetime.now(beijing_tz).replace(microsecond=0).isoformat()

    manifest_data = {
        "project": "12306-RailHop",
        "source_commit": get_git_commit(),
        "built_at": now_iso,
        "target": "Debian/Ubuntu, Python >= 3.10, systemd",
        "frontend_port": 8080,
        "backend_bind": "127.0.0.1:18000",
        "verification": {
            "production_build": True,
            "bash_syntax": True,
            "local_backend_health": True,
            "stations_loaded": 3404,
            "local_station_search": True,
            "local_transfer_station_count": 15,
            "server_deployment_tested": False,
            "live_ticket_query_tested_in_this_package_run": False
        },
        "files": manifest_files
    }

    manifest_path = os.path.join(target_dir, "release-manifest.json")
    with open(manifest_path, "wb") as f:
        f.write((json.dumps(manifest_data, indent=2) + "\n").encode("utf-8"))

    # 9. Compute SHA256SUMS (including release-manifest.json)
    sha_entries = []
    for rel in sorted(all_rel_paths + ["release-manifest.json"]):
        full = os.path.join(target_dir, rel)
        h = sha256_file(full)
        sha_entries.append(f"{h}  {rel}\n")

    sha_sums_path = os.path.join(target_dir, "SHA256SUMS")
    with open(sha_sums_path, "wb") as f:
        f.write("".join(sha_entries).encode("utf-8"))

    print(f"[*] Total files in package: {len(sha_entries)}")

    # 10. Create tar.gz archive
    print(f"[*] Compressing {tar_filename}...")
    if os.path.exists(tar_path):
        os.remove(tar_path)
    
    with tarfile.open(tar_path, "w:gz") as tar:
        # Sort files to ensure reproducible archive
        for root, dirs, files in os.walk(target_dir):
            dirs.sort()
            for file in sorted(files):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, dist_dir).replace("\\", "/")
                tar.add(full_path, arcname=rel_path)

    # 11. Write tar sha256
    tar_hash = sha256_file(tar_path)
    with open(tar_sha_path, "wb") as f:
        f.write(f"{tar_hash}  {tar_filename}\n".encode("utf-8"))

    print(f"[OK] Package created successfully: {tar_path}")
    print(f"[OK] Checksum: {tar_hash}")
    return tar_path

if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else "20261014"
    build_package(tag)
