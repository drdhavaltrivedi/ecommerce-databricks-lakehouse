#!/usr/bin/env python3
"""Stream a CSV member out of a local zip, split into <5GiB parts (each with
the header line), and upload each part to a UC Volume via the Files API.
Only one part (~1GB) is ever buffered on local disk at a time.

Uploads are retried and size-verified. A multi-minute PUT over a consumer
connection will occasionally die mid-stream with a broken pipe; without a retry
the whole multi-GB run is lost at the last part. Verification matters as much as
the retry -- a PUT can return success while the object is short, and a truncated
CSV in the volume would be silently ingested as real data."""
import os, sys, zipfile, http.client, ssl, time, urllib.request
from urllib.parse import urlparse

HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]
PART_SIZE = 1_000_000_000  # ~1GB per part, well under 5GiB limit
MAX_ATTEMPTS = 5


def remote_size(volume_path):
    """Size of the object in the volume, or None if it is not there."""
    req = urllib.request.Request(f"{HOST}/api/2.0/fs/files{volume_path}", method="HEAD")
    req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req) as r:
            return int(r.headers.get("Content-Length", -1))
    except Exception:
        return None


def _put_once(local_path, volume_path):
    parsed = urlparse(HOST)
    size = os.path.getsize(local_path)
    conn = http.client.HTTPSConnection(
        parsed.netloc, context=ssl.create_default_context(), timeout=600
    )
    conn.putrequest("PUT", f"/api/2.0/fs/files{volume_path}?overwrite=true")
    conn.putheader("Authorization", f"Bearer {TOKEN}")
    conn.putheader("Content-Type", "application/octet-stream")
    conn.putheader("Content-Length", str(size))
    conn.endheaders()
    with open(local_path, "rb") as f:
        while True:
            chunk = f.read(4 * 1024 * 1024)
            if not chunk:
                break
            conn.send(chunk)
    resp = conn.getresponse()
    body = resp.read().decode()
    conn.close()
    if resp.status >= 300:
        raise RuntimeError(f"HTTP {resp.status}: {body[:300]}")
    return resp.status


def put_file(local_path, volume_path):
    expected = os.path.getsize(local_path)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        # skip work already done -- makes the whole run resumable after a crash
        if remote_size(volume_path) == expected:
            print(f"  {volume_path} already uploaded ({expected/1e6:.0f} MB), skipping")
            return
        try:
            status = _put_once(local_path, volume_path)
            time.sleep(3)  # the volume listing is not instantly consistent
            actual = remote_size(volume_path)
            if actual == expected:
                print(f"  uploaded {volume_path} ({expected/1e6:.0f} MB) -> {status}")
                return
            print(f"  size mismatch after upload: remote={actual}, expected={expected}")
        except Exception as e:
            print(f"  attempt {attempt}/{MAX_ATTEMPTS} failed: {type(e).__name__}: {e}")
        if attempt < MAX_ATTEMPTS:
            backoff = min(30, 2 ** attempt)
            print(f"  retrying in {backoff}s")
            time.sleep(backoff)
    raise SystemExit(f"Upload of {volume_path} failed after {MAX_ATTEMPTS} attempts")

def split_and_upload(zip_path, member_name, volume_dir, tmp_dir):
    os.makedirs(tmp_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        info = zf.getinfo(member_name)
        total = info.file_size
        print(f"Splitting {member_name} ({total/1e9:.2f} GB) into ~{PART_SIZE/1e9:.1f}GB parts")
        with zf.open(member_name) as src:
            header = src.readline()
            part_idx = 0
            sent_total = 0
            while True:
                part_path = os.path.join(tmp_dir, f"part-{part_idx:04d}.csv")
                with open(part_path, "wb") as pf:
                    pf.write(header)
                    part_bytes = len(header)
                    eof = False
                    while part_bytes < PART_SIZE:
                        line = src.readline()
                        if not line:
                            eof = True
                            break
                        pf.write(line)
                        part_bytes += len(line)
                sent_total += part_bytes
                pct = sent_total / total * 100
                print(f"part {part_idx}: {part_bytes/1e6:.0f} MB written ({pct:.1f}% of stream consumed)")
                put_file(part_path, f"{volume_dir}/part-{part_idx:04d}.csv")
                os.remove(part_path)
                part_idx += 1
                if eof:
                    break
    print("All parts uploaded.")

if __name__ == "__main__":
    zip_path, member_name, volume_dir, tmp_dir = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    split_and_upload(zip_path, member_name, volume_dir, tmp_dir)
