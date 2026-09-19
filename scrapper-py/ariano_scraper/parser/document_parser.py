"""
Parser de documento: transforma texto normalizado (por página) em dados
estruturados, usando SOMENTE regras determinísticas (regex + detecção
de seções + lista local de competências conhecidas). Nenhum LLM é
usado aqui.

Organizado em três blocos, nesta ordem:

    1. Detecção de seções (headings tolerantes a variação de redação);
    2. Extração por regex (datas, valores monetários, prazo,
       organização, título);
    3. Reconhecimento de competências via known_tags.json;

`parse_document()` orquestra os três blocos e devolve as peças que
`main.py` usa para montar o `FinalDocument` (schemas/document_schema.py).
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

from pdf.extractor import ExtractedDocument
from schemas.document_schema import (
    Competency,
    Confidence,
    DocumentInfo,
    Financial,
    Requirement,
    Section,
    TrackedValue,
)
from utils.text import strip_accents

_HEADING_DEFINITIONS: List[Tuple[str, List[str]]] = [
    ("OBJETIVO", ["OBJETIVO", "OBJETO"]),
    ("PÚBLICO-ALVO", ["PUBLICO-ALVO", "PUBLICO ALVO"]),
    ("REQUISITOS", ["REQUISITOS"]),
    ("CRITÉRIOS DE ELEGIBILIDADE", ["CRITERIOS DE ELEGIBILIDADE"]),
    ("PRAZOS", ["PRAZOS"]),
    ("CRONOGRAMA", ["CRONOGRAMA"]),
    ("RECURSOS", ["RECURSOS"]),
    ("VALOR", ["VALOR"]),
    ("ORÇAMENTO", ["ORCAMENTO"]),
]

_LEADING_NUMBERING_RE = re.compile(r"^\d+\s*[.\)\-]\s*")
_LEADING_ARTICLE_RE = re.compile(r"^(DO|DA|DOS|DAS)\s+", re.IGNORECASE)

_MAX_HEADING_LINE_LENGTH = 60


def _clean_heading_candidate(line: str) -> Optional[str]:
    s = line.strip().rstrip(":").strip()
    if not s or len(s) > _MAX_HEADING_LINE_LENGTH:
        return None
    s = _LEADING_NUMBERING_RE.sub("", s)
    s = _LEADING_ARTICLE_RE.sub("", s)
    s = strip_accents(s).upper().strip()
    return s or None


def is_heading_line(line: str) -> Optional[str]:
    candidate = _clean_heading_candidate(line)
    if not candidate:
        return None
    for canonical, variants in _HEADING_DEFINITIONS:
        if candidate in variants:
            return canonical
    return None


def detect_sections(document: ExtractedDocument) -> List[Section]:
 
    lines: List[Tuple[int, str]] = []
    for page in document.pages:
        for raw_line in page.text.split("\n"):
            lines.append((page.page, raw_line))

    heading_positions: List[Tuple[int, str, int]] = []
    for idx, (page, line) in enumerate(lines):
        canonical = is_heading_line(line)
        if canonical:
            heading_positions.append((idx, canonical, page))

    sections: List[Section] = []
    for i, (idx, canonical, page) in enumerate(heading_positions):
        end_idx = heading_positions[i + 1][0] if i + 1 < len(heading_positions) else len(lines)
        body_lines = [text for _, text in lines[idx + 1 : end_idx]]
        body_text = "\n".join(line for line in body_lines if line.strip()).strip()
        if body_text:
            sections.append(Section(heading=canonical, page=page, text=body_text))

    return sections

_PT_MONTHS = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}

_DATE_NUMERIC_RE = re.compile(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b")
_DATE_TEXTUAL_RE = re.compile(r"(\d{1,2})\s+de\s+([A-Za-zçÇÀ-ÿ]+)\s+de\s+(\d{4})", re.IGNORECASE)

_MONEY_WITH_CURRENCY_RE = re.compile(r"R\$\s*\d{1,3}(?:\.\d{3})*(?:,\d{2})?")
_MONEY_BARE_RE = re.compile(r"\b\d{1,3}(?:\.\d{3})+,\d{2}\b")

_DEADLINE_KEYWORDS = ["prazo", "inscricao", "inscricoes", "submissao", "encerramento", "deadline"]
_PUBLICATION_KEYWORDS = ["publicado em", "data de publicacao", "publicacao"]
_FINANCIAL_KEYWORDS = ["orcamento", "valor", "recursos", "investimento", "financeiro"]

_LAW_CITATION_RE = re.compile(r"(lei|decreto|portaria|instrucao normativa|resolucao)\s+n[o°º]?\.?\s*[\d.,/-]+")

_ORG_RE = re.compile(
    r"\b(Secretaria|Minist[ée]rio|Prefeitura|Universidade|Instituto|"
    r"Funda[cç][aã]o|Ag[eê]ncia|C[aâ]mara)\s+[^\n.,;:]{2,80}",
    re.IGNORECASE,
)


def parse_brl_number(raw: str) -> float:
   
    cleaned = raw.replace("R$", "").strip().replace(" ", "")
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(".", "")
    return float(cleaned)


def find_dates_in_text(text: str) -> List[Tuple[date, int]]:
   
    results: List[Tuple[date, int]] = []

    for m in _DATE_NUMERIC_RE.finditer(text):
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            results.append((date(year, month, day), m.start()))
        except ValueError:
            continue

    for m in _DATE_TEXTUAL_RE.finditer(text):
        day = int(m.group(1))
        month = _PT_MONTHS.get(strip_accents(m.group(2)).lower())
        year = int(m.group(3))
        if month:
            try:
                results.append((date(year, month, day), m.start()))
            except ValueError:
                continue

    results.sort(key=lambda item: item[1])
    return results


def find_money_in_text(text: str) -> List[Tuple[float, int]]:
   
    matches: List[Tuple[float, int]] = []
    covered_spans: List[Tuple[int, int]] = []

    for m in _MONEY_WITH_CURRENCY_RE.finditer(text):
        try:
            value = parse_brl_number(m.group(0))
        except ValueError:
            continue
        matches.append((value, m.start()))
        covered_spans.append((m.start(), m.end()))

    for m in _MONEY_BARE_RE.finditer(text):
        if any(m.start() >= s and m.end() <= e for s, e in covered_spans):
            continue  
        try:
            value = parse_brl_number(m.group(0))
        except ValueError:
            continue
        matches.append((value, m.start()))

    matches.sort(key=lambda item: item[1])
    return matches


def _split_sentences_with_offsets(text: str) -> List[Tuple[str, int]]:
   
    sentences: List[Tuple[str, int]] = []
    last = 0
   
    for m in re.finditer(r"(?:(?<!\d)[.!?](?!\d))+\s*|\n+\s*", text):
        end = m.start()
        if end > last:
            sentences.append((text[last:end], last))
        last = m.end()
    if last < len(text):
        sentences.append((text[last:], last))
    return sentences


def _is_law_citation_context(sentence: str, position: int) -> bool:
  
    before = strip_accents(sentence[:position]).lower()
    return bool(_LAW_CITATION_RE.search(before[-80:]))


def _find_date_near(page_text: str, keywords: List[str]) -> Optional[date]:
   
    for sentence, _offset in _split_sentences_with_offsets(page_text):
        lower_sentence = strip_accents(sentence).lower()
        if not any(kw in lower_sentence for kw in keywords):
            continue
        for value, local_start in find_dates_in_text(sentence):
            if _is_law_citation_context(sentence, local_start):
                continue
            return value
    return None


def _find_money_near(page_text: str, keywords: List[str]) -> Optional[float]:
   
    for sentence, _offset in _split_sentences_with_offsets(page_text):
        lower_sentence = strip_accents(sentence).lower()
        if not any(kw in lower_sentence for kw in keywords):
            continue
        candidates = find_money_in_text(sentence)
        if candidates:
            return candidates[0][0]
    return None


def extract_submission_deadline(document: ExtractedDocument) -> Optional[TrackedValue]:
    for page in document.pages:
        value = _find_date_near(page.text, _DEADLINE_KEYWORDS)
        if value is not None:
            return TrackedValue(value=value, confidence=Confidence.HIGH, source_page=page.page)
    return None


def extract_publication_date(document: ExtractedDocument) -> Optional[TrackedValue]:
    for page in document.pages:
        value = _find_date_near(page.text, _PUBLICATION_KEYWORDS)
        if value is not None:
            return TrackedValue(value=value, confidence=Confidence.MEDIUM, source_page=page.page)
    return None


def extract_budget(document: ExtractedDocument) -> Optional[TrackedValue]:
   
    for page in document.pages:
        value = _find_money_near(page.text, _FINANCIAL_KEYWORDS)
        if value is not None:
            return TrackedValue(value=value, confidence=Confidence.HIGH, source_page=page.page)
    return None


def extract_organization(document: ExtractedDocument) -> Optional[TrackedValue]:
    
    for page in document.pages[:2]:
        m = _ORG_RE.search(page.text)
        if m:
            return TrackedValue(value=m.group(0).strip(), confidence=Confidence.MEDIUM, source_page=page.page)
    return None


def extract_title(document: ExtractedDocument, pdf_title_metadata: Optional[str]) -> Optional[TrackedValue]:
    if pdf_title_metadata and len(pdf_title_metadata.strip()) > 3:
        return TrackedValue(value=pdf_title_metadata.strip(), confidence=Confidence.HIGH, source_page=1)

    if document.pages:
        first_page_lines = [line.strip() for line in document.pages[0].text.split("\n") if line.strip()]
        for line in first_page_lines:
            if 5 <= len(line) <= 150 and not is_heading_line(line):
                return TrackedValue(value=line, confidence=Confidence.MEDIUM, source_page=1)

    return None

_REQUIREMENT_HEADINGS = {"REQUISITOS", "CRITÉRIOS DE ELEGIBILIDADE"}


def extract_requirements(sections: List[Section]) -> List[Requirement]:
    requirements: List[Requirement] = []
    for section in sections:
        if section.heading not in _REQUIREMENT_HEADINGS:
            continue
        for raw_line in section.text.split("\n"):
            line = raw_line.strip(" -•\t")
            if len(line) >= 5:
                requirements.append(Requirement(text=line, confidence=Confidence.MEDIUM, source_page=section.page))
    return requirements

_DEFAULT_KNOWN_TAGS_PATH = Path(__file__).parent / "known_tags.json"


def load_known_tags(path: Optional[Path] = None) -> List[dict]:
    tags_path = path or _DEFAULT_KNOWN_TAGS_PATH
    with open(tags_path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_competencies(document: ExtractedDocument, known_tags: List[dict]) -> List[Competency]:
 
    competencies: List[Competency] = []

    for tag in known_tags:
        code, name, aliases = tag["code"], tag["name"], tag["aliases"]
        match_found = None

        for page in document.pages:
            for alias in aliases:
                pattern = re.compile(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", re.IGNORECASE)
                m = pattern.search(page.text)
                if m:
                    confidence = Confidence.HIGH if len(alias) >= 4 else Confidence.MEDIUM
                    match_found = Competency(
                        code=code,
                        name=name,
                        confidence=confidence,
                        source_page=page.page,
                        matched_text=m.group(0),
                    )
                    break
            if match_found:
                break

        if match_found:
            competencies.append(match_found)

    return competencies

def parse_document(
    document: ExtractedDocument,
    pdf_title_metadata: Optional[str] = None,
    known_tags_path: Optional[Path] = None,
) -> Tuple[DocumentInfo, List[Requirement], List[Competency], Financial, List[Section], List[str]]:
 
    warnings: List[str] = []

    sections = detect_sections(document)

    title = extract_title(document, pdf_title_metadata)
    if title is None:
        warnings.append("Não foi possível identificar um título para o documento.")

    organization = extract_organization(document)
    if organization is None:
        warnings.append("Não foi possível identificar a organização responsável.")

    submission_deadline = extract_submission_deadline(document)
    if submission_deadline is None:
        warnings.append("Não foi possível identificar o prazo de submissão/inscrição.")

    publication_date = extract_publication_date(document)

    budget = extract_budget(document)
    if budget is None:
        warnings.append("Não foi possível identificar um valor financeiro (orçamento).")

    requirements = extract_requirements(sections)
    if not requirements:
        warnings.append(
            "Nenhum requisito foi identificado (seção REQUISITOS/CRITÉRIOS DE "
            "ELEGIBILIDADE não encontrada ou vazia)."
        )

    known_tags = load_known_tags(known_tags_path)
    competencies = extract_competencies(document, known_tags)
    if not competencies:
        warnings.append("Nenhuma competência conhecida foi identificada no texto.")

    document_info = DocumentInfo(
        title=title,
        organization=organization,
        publication_date=publication_date,
        submission_deadline=submission_deadline,
    )
    financial = Financial(budget=budget, currency="BRL")

    return document_info, requirements, competencies, financial, sections, warnings
