"""
Trava de segurança da ponte ctypes.

bindings.py declara structs à mão. Se domain.h mudar (campo novo, tipo
diferente, ordem trocada) e este arquivo não mudar junto, a leitura de memória
sai silenciosamente errada — scores plausíveis e incorretos, que é o pior tipo
de bug. Este teste compila um programa C que imprime sizeof/offsetof de cada
campo e compara com o que o ctypes acha. Qualquer divergência falha aqui.

Requer um compilador C (cc/gcc) e os headers do motor.
"""

from __future__ import annotations

import ctypes
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from ariano_api.engine import bindings as b

ROOT = Path(__file__).resolve().parents[2]
INCLUDE = ROOT / "Matching-ariano-c" / "matching_engine" / "include"

# struct C -> (classe ctypes, [campos])
STRUCTS = {
    "Tag": (b.Tag, ["id", "code"]),
    "ActorTag": (b.ActorTag, ["tag_id", "weight"]),
    "Actor": (b.Actor, ["id", "type", "status", "tags", "tag_count"]),
    "DemandTag": (b.DemandTag, ["tag_id", "type", "weight"]),
    "Demand": (b.Demand, ["id", "tags", "tag_count"]),
    "TagRelationship": (
        b.TagRelationship,
        ["source_tag_id", "target_tag_id", "type", "weight"],
    ),
    "RelationSet": (b.RelationSet, ["items", "count"]),
    "MatchDetail": (
        b.MatchDetail,
        [
            "demand_tag_id",
            "tag_type",
            "match",
            "actor_tag_id",
            "relation_type",
            "demand_weight",
            "actor_weight",
            "relation_weight",
            "coverage",
        ],
    ),
    "MatchResult": (
        b.MatchResult,
        [
            "actor_id",
            "demand_id",
            "status",
            "score",
            "required_score",
            "desirable_score",
            "match_class",
            "required_count",
            "desirable_count",
            "required_missing_count",
            "details",
            "algorithm_version",
        ],
    ),
    "MatchConfig": (b.MatchConfig, ["desirable_share"]),
    "BatchOptions": (b.BatchOptions, ["threshold", "top_k"]),
    "BatchResult": (
        b.BatchResult,
        ["status", "evaluated_count", "passed_count", "count", "results"],
    ),
}


def _c_layout() -> dict:
    lines = [
        '#include <stdio.h>',
        '#include <stddef.h>',
        '#include "batch.h"',
        '#include "matcher.h"',
        '#include "domain.h"',
        "int main(void) {",
        '    printf("{");',
    ]
    for si, (name, (_, fields)) in enumerate(STRUCTS.items()):
        sep = "" if si == 0 else ","
        lines.append(
            f'    printf("{sep}\\"{name}\\":{{\\"__size__\\":%zu", sizeof({name}));'
        )
        for f in fields:
            lines.append(
                f'    printf(",\\"{f}\\":%zu", offsetof({name}, {f}));'
            )
        lines.append('    printf("}");')
    lines += ['    printf("}\\n");', "    return 0;", "}"]

    cc = shutil.which("cc") or shutil.which("gcc")
    if cc is None:
        pytest.skip("nenhum compilador C disponível")

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "abi.c"
        exe = Path(tmp) / "abi"
        src.write_text("\n".join(lines))
        subprocess.run(
            [cc, "-std=c17", f"-I{INCLUDE}", str(src), "-o", str(exe)],
            check=True,
            capture_output=True,
        )
        proc = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
    return json.loads(proc.stdout)


@pytest.mark.parametrize("name", list(STRUCTS))
def test_struct_layout_matches_c(name: str) -> None:
    layout = _c_layout()[name]
    py_cls, fields = STRUCTS[name]

    assert ctypes.sizeof(py_cls) == layout["__size__"], (
        f"sizeof({name}) difere entre C e ctypes — bindings.py está desatualizado"
    )
    for field in fields:
        assert getattr(py_cls, field).offset == layout[field], (
            f"offsetof({name}.{field}) difere entre C e ctypes"
        )
