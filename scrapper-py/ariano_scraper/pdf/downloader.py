from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from utils.errors import PipelineError
from utils.hashing import sha256_of_file

DEFAULT_TIMEOUT = (10, 30)
DEFAULT_MAX_BYTES = 50 * 1024 * 1024 
DEFAULT_MAX_REDIRECTS = 5
_ACCEPTED_CONTENT_TYPES = ("application/pdf",)


class DownloadError(PipelineError):
    def __init__(self, reason: str):
        super().__init__(stage="DOWNLOAD", reason=reason)


@dataclass
class DownloadResult:
    file_path: Path
    document_hash: str
    content_type: Optional[str]


def download_pdf(
    url: str,
    destination_dir: Path,
    filename: Optional[str] = None,
    timeout=DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> DownloadResult:
 
    session = requests.Session()
    session.max_redirects = DEFAULT_MAX_REDIRECTS

    try:
        response = session.get(url, timeout=timeout, stream=True)
    except requests.exceptions.RequestException as exc:
        raise DownloadError(f"Request failed for {url}: {exc}") from exc

    if response.status_code != 200:
        raise DownloadError(f"Unexpected HTTP status {response.status_code} for {url}")

    content_type = response.headers.get("Content-Type", "")
    if not any(ct in content_type for ct in _ACCEPTED_CONTENT_TYPES):
        raise DownloadError(
            f"Unexpected Content-Type '{content_type}' for {url} "
            f"(expected one of {_ACCEPTED_CONTENT_TYPES})"
        )

    destination_dir.mkdir(parents=True, exist_ok=True)
    name = filename or Path(url.split("?")[0]).name or "document.pdf"
    file_path = destination_dir / name

    total_bytes = 0
    try:
        with open(file_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise DownloadError(
                        f"File exceeds maximum accepted size "
                        f"({max_bytes} bytes) while downloading {url}"
                    )
                f.write(chunk)
    except DownloadError:
        file_path.unlink(missing_ok=True)
        raise

    if total_bytes == 0:
        file_path.unlink(missing_ok=True)
        raise DownloadError(f"Downloaded file is empty: {url}")

    return DownloadResult(
        file_path=file_path,
        document_hash=sha256_of_file(file_path),
        content_type=content_type,
    )
