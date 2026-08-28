"""
Downloads the Low Carbon London smart meter data from the London Datastore.

The main zip is about 765 MB and unpacks to a ~10 GB CSV with 167 million rows,
so this takes a while. Everything lands in data/raw and is skipped if already there.
"""

import os
import requests

# The datastore ZIP is Deflate64 (ZIP method 9), which the standard library's
# zipfile module cannot read. zipfile64 patches the familiar zipfile API.
import zipfile64.zipfile as zipfile

DATA_DIR = "data/raw"

FILES = {
    "LCL-FullData.zip": "https://data.london.gov.uk/download/vqm0d/3527bf39-d93e-4071-8451-df2ade1ea4f2/LCL-FullData.zip",
    "Tariffs.xlsx": "https://data.london.gov.uk/download/vqm0d/14855047-44c2-4856-8a48-e5649200e6ce/Tariffs.xlsx",
}


def download(name, url):
    path = os.path.join(DATA_DIR, name)
    if os.path.exists(path):
        print("already have", name, round(os.path.getsize(path) / 1e6, 1), "MB")
        return path

    tmp = path + ".part"
    done = 0
    headers = {}
    if os.path.exists(tmp):
        done = os.path.getsize(tmp)
        headers["Range"] = "bytes=%d-" % done
        print("resuming", name, "from", round(done / 1e6, 1), "MB")

    r = requests.get(url, headers=headers, stream=True, timeout=60)
    r.raise_for_status()

    total = int(r.headers.get("Content-Length", 0)) + done
    with open(tmp, "ab") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)
            done += len(chunk)
            if total:
                print("\r  %s  %.1f / %.1f MB" % (name, done / 1e6, total / 1e6), end="")
    print()
    os.rename(tmp, path)
    return path


def unzip(path):
    with zipfile.ZipFile(path) as z:
        for member in z.namelist():
            out = os.path.join(DATA_DIR, os.path.basename(member))
            if member.endswith("/"):
                continue
            if os.path.exists(out):
                print("already extracted", os.path.basename(member))
                continue
            print("extracting", member, "...")
            with z.open(member) as src, open(out, "wb") as dst:
                while True:
                    buf = src.read(1024 * 1024 * 8)
                    if not buf:
                        break
                    dst.write(buf)
            print("  ->", out, round(os.path.getsize(out) / 1e9, 2), "GB")


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    for name, url in FILES.items():
        p = download(name, url)
        if name.endswith(".zip"):
            unzip(p)
    print("done")
