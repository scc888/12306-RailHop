import os
import subprocess
import sys

def main():
    raw = os.environ.get("SSH_KEY", "").strip()
    if not raw:
        print("::error title=Missing Secret::SERVER_SSH_KEY secret is empty or not set in GitHub Secrets!", file=sys.stderr)
        sys.exit(1)

    raw = raw.strip('\'"')

    begin_marker = "-----BEGIN OPENSSH PRIVATE KEY-----"
    end_marker = "-----END OPENSSH PRIVATE KEY-----"

    if begin_marker not in raw or end_marker not in raw:
        if "-----BEGIN RSA PRIVATE KEY-----" in raw:
            begin_marker = "-----BEGIN RSA PRIVATE KEY-----"
            end_marker = "-----END RSA PRIVATE KEY-----"
        elif raw.startswith("ssh-"):
            print("::error title=Public Key Detected::SERVER_SSH_KEY in GitHub Secrets is a PUBLIC key. It must be the PRIVATE key (starts with '-----BEGIN OPENSSH PRIVATE KEY-----').", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"::error title=Invalid Key Format::Could not find BEGIN/END private key markers in SERVER_SSH_KEY. Header preview: {repr(raw[:40])}", file=sys.stderr)
            sys.exit(1)

    start_pos = raw.find(begin_marker)
    end_pos = raw.find(end_marker) + len(end_marker)
    block = raw[start_pos:end_pos]

    # Extract base64 body between markers
    body = block[len(begin_marker):-len(end_marker)]
    body = body.replace("\\n", "").replace("\\r", "")
    body = "".join(body.split())

    # Re-chunk body into 64-char lines
    chunked_body = "\n".join(body[i:i+64] for i in range(0, len(body), 64))
    formatted_key = f"{begin_marker}\n{chunked_body}\n{end_marker}\n"

    ssh_dir = os.path.expanduser("~/.ssh")
    os.makedirs(ssh_dir, exist_ok=True)
    key_file = os.path.join(ssh_dir, "deploy_key")

    with open(key_file, "wb") as f:
        f.write(formatted_key.encode("utf-8"))

    try:
        os.chmod(key_file, 0o600)
    except Exception:
        pass

    # Validate with ssh-keygen
    res = subprocess.run(["ssh-keygen", "-lf", key_file], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"::error title=Private Key Decode Failed::ssh-keygen failed: {res.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    fp = res.stdout.strip()
    print(f"::notice title=Key Fingerprint::{fp}")
    print(f"[OK] Successfully verified deploy key: {fp}")

if __name__ == "__main__":
    main()
