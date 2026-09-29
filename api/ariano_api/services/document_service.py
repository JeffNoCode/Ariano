from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRAPER_DIR = Path(
    os.environ.get(
        "ARIANO_SCRAPER_DIR",
        Path(__file__).resolve().parents[3] / "scrapper-py" / "ariano_scraper",
    )
)
SCRAPER_PYTHON = os.environ.get("ARIANO_SCRAPER_PYTHON", sys.executable)
SCRAPER_TIMEOUT = int(os.environ.get("ARIANO_SCRAPER_TIMEOUT", "120"))


class ScraperError(Exception):
    """O pipeline do scraper falhou. `stderr` traz a mensagem tratada da CLI."""

    def __init__(self, message: str, returncode: int):
        super().__init__(message)
        self.returncode = returncode


def run_scraper(pdf_bytes: bytes, filename: str = "upload.pdf") -> dict:
    if not SCRAPER_DIR.exists():
        raise ScraperError(f"scraper não encontrado em {SCRAPER_DIR}", -1)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pdf_path = tmp_path / (Path(filename).name or "upload.pdf")
        pdf_path.write_bytes(pdf_bytes)
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        proc = subprocess.run(
            [SCRAPER_PYTHON, "main.py", str(pdf_path), "--output", str(out_dir)],
            cwd=SCRAPER_DIR,
            capture_output=True,
            text=True,
            timeout=SCRAPER_TIMEOUT,
        )
        if proc.returncode != 0:
            raise ScraperError(
                (proc.stderr or proc.stdout or "erro desconhecido").strip(),
                proc.returncode,
            )

        produced = sorted(out_dir.glob("*.json"))
        if not produced:
            raise ScraperError("o scraper terminou com sucesso mas não gerou JSON", 0)
        return json.loads(produced[0].read_text(encoding="utf-8"))
