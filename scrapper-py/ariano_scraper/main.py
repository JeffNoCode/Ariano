from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from parser.document_parser import parse_document
from pdf.extractor import extract_text_by_page, get_metadata_title
from pdf.normalizer import normalize_document
from pdf.validator import validate_file_on_disk, validate_pdf_content
from schemas.document_schema import FinalDocument, ProcessingMetadata
from storage.json_writer import write_json
from utils.errors import PipelineError, SchemaValidationError
from utils.hashing import sha256_of_file
from utils.logging import setup_logging
from utils.version import PARSER_VERSION


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ariano-scraper",
        description="ARIANO — extrai e estrutura informações de um documento PDF local.",
    )
    parser.add_argument(
        "pdf_path",
        type=str,
        help="Caminho para o arquivo PDF a ser processado (ex.: ./documents/edital.pdf).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="output",
        help="Diretório onde o JSON resultante será salvo (padrão: ./output).",
    )
    parser.add_argument(
        "--known-tags",
        type=str,
        default=None,
        help="Caminho alternativo para o arquivo known_tags.json (padrão: parser/known_tags.json).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Ativa logs de debug.",
    )
    return parser


def process_pdf(pdf_path: Path, output_dir: Path, known_tags_path: Path | None, logger) -> Path:

    validate_file_on_disk(pdf_path)

    validation_result = validate_pdf_content(pdf_path)

    extraction_warnings: list[str] = []
    if validation_result.extraction_method.value == "ocr_required":
        message = (
            "Documento parece ser escaneado (sem camada de texto nativa "
            f"em {validation_result.empty_page_ratio:.0%} das páginas). "
            "OCR ainda não está implementado neste MVP; a extração "
            "prosseguirá com o texto nativo disponível, que pode ser "
            "parcial ou vazio."
        )
        logger.warning(message)
        extraction_warnings.append(message)

    document_hash = sha256_of_file(pdf_path)
    
    raw_document = extract_text_by_page(pdf_path)

    normalized_document = normalize_document(raw_document)

    pdf_title_metadata = get_metadata_title(pdf_path)
    document_info, requirements, competencies, financial, sections, parse_warnings = parse_document(
        normalized_document,
        pdf_title_metadata=pdf_title_metadata,
        known_tags_path=known_tags_path,
    )
    extraction_warnings.extend(parse_warnings)

    metadata = ProcessingMetadata(
        source_url=None,
        source_file=str(pdf_path),
        document_hash=document_hash,
        processed_at=datetime.now(timezone.utc),
        parser_version=PARSER_VERSION,
        extraction_method=validation_result.extraction_method,
        ocr_used=False,
        page_count=validation_result.page_count,
    )

    try:
        final_document = FinalDocument(
            processing_metadata=metadata,
            document=document_info,
            requirements=requirements,
            competencies=competencies,
            financial=financial,
            sections=sections,
            extraction_warnings=extraction_warnings,
        )
    except ValidationError as exc:
        raise SchemaValidationError(str(exc)) from exc

    output_path = output_dir / f"{pdf_path.stem}.json"
    write_json(final_document, output_path)

    return output_path, final_document


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logger = setup_logging(verbose=args.verbose)

    pdf_path = Path(args.pdf_path)
    output_dir = Path(args.output)
    known_tags_path = Path(args.known_tags) if args.known_tags else None

    try:
        output_path, final_document = process_pdf(pdf_path, output_dir, known_tags_path, logger)
    except PipelineError as exc:
        logger.error(
            "Failed to process document\n"
            f"Stage: {exc.stage}\n"
            f"Reason: {exc.reason}\n"
            f"File: {pdf_path}"
        )
        return 1
    except Exception as exc:
        logger.error(f"Unexpected error while processing {pdf_path}: {exc}")
        return 2

    logger.info(f"Document processed successfully: {pdf_path}")
    logger.info(f"JSON saved to: {output_path}")

    title = final_document.document.title.value if final_document.document.title else "(não identificado)"
    logger.info(f"Title: {title}")
    logger.info(f"Competencies found: {len(final_document.competencies)}")
    logger.info(f"Requirements found: {len(final_document.requirements)}")
    logger.info(f"Sections found: {len(final_document.sections)}")
    if final_document.extraction_warnings:
        logger.info(f"Warnings: {len(final_document.extraction_warnings)} (see JSON for details)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
