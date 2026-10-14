import os
import subprocess
import sys

def main():
    raw = os.environ.get("SSH_KEY", "").strip()
    if not raw:
        print("::error title=Missing Secret::SERVER_SSH_KEY secret is empty or not set!", file=sys.stderr)
        sys.exit(1)

    # Strip enclosing quotes
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        raw = raw[1:-1].strip()

    # Check if user accidentally pasted public key
    if raw.startswith("ssh-"):
        print("::error title=Public Key Detected::SERVER_SSH_KEY in GitHub Secrets is a PUBLIC key. It must be the PRIVATE key (starts with '-----BEGIN OPENSSH PRIVATE KEY-----').", file=sys.stderr)
        sys.exit(1)

    # Check if literal \n was used instead of actual newlines
    if "\\n" in raw and "\n" not in raw:
        raw = raw.replace("\\r", "").replace("\\n", "\n")
    else:
        raw = raw.replace("\r\n", "\n")

    # If it's on a single line and contains spaces instead of newlines between headers
    if "BEGIN OPENSSH PRIVATE KEY" in raw and "\n" not in raw.strip():
        raw = raw.replace("-----BEGIN OPENSSH PRIVATE KEY-----", "-----BEGIN OPENSSH PRIVATE KEY-----\n")
        raw = raw.replace("-----END OPENSSH PRIVATE KEY-----", "\n-----END OPENSSH PRIVATE KEY-----\n")
        parts = raw.split("\n")
        if len(parts) >= 3:
            middle = parts[1].strip().replace(" ", "\n")
            raw = parts[0] + "\n" + middle + "\n" + parts[2].strip() + "\n"

    raw = raw.strip() + "\n"

    ssh_dir = os.path.expanduser("~/.ssh")
    os.makedirs(ssh_dir, exist_ok=True)
    key_file = os.path.join(ssh_dir, "deploy_key")

    with open(key_file, "wb") as f:
        f.write(raw.encode("utf-8"))
    
    try:
        os.chmod(key_file, 0o600)
    except Exception:
        pass

    # Verify key with ssh-keygen
    res = subprocess.run(["ssh-keygen", "-lf", key_file], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"::error title=Invalid Private Key::ssh-keygen failed to read private key: {res.stderr.strip()}", file=sys.stderr)
        print(f"Key preview: {raw[:35]}... (total lines: {len(raw.splitlines())})", file=sys.stderr)
        sys.exit(1)
    
    fp = res.stdout.strip()
    print(f"::notice title=Key Fingerprint::{fp}")
    print(f"[OK] Valid deployment key loaded with fingerprint: {fp}")

if __name__ == "__main__":
    main()
