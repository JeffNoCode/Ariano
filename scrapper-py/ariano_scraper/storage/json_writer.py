from __future__ import annotations

import json
from pathlib import Path

from schemas.document_schema import FinalDocument


def write_json(document: FinalDocument, output_path: Path) -> Path:
   
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = document.model_dump(mode="json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return output_path
