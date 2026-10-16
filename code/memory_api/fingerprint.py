"""HW6 - a short fingerprint of the memory_api source files, so a run can prove which code produced it
(the Part 3 sweep compares the container's fingerprint with the one computed from the repo)."""
from __future__ import annotations

import hashlib
from pathlib import Path


def source_fingerprint(package_dir: Path | None = None) -> str:
    package_dir = package_dir or Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(list(package_dir.glob("*.py")) + list(package_dir.glob("*.html"))):
        digest.update(path.name.encode())
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()[:16]
