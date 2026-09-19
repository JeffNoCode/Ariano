from datetime import date

from parser.document_parser import (
    find_dates_in_text,
    find_money_in_text,
    parse_brl_number,
)


def test_finds_numeric_date_with_slash():
    dates = find_dates_in_text("Prazo de inscrição: 30/10/2026")
    assert dates[0][0] == date(2026, 10, 30)


def test_finds_numeric_date_with_dash():
    dates = find_dates_in_text("Encerramento em 30-10-2026")
    assert dates[0][0] == date(2026, 10, 30)


def test_finds_textual_date():
    dates = find_dates_in_text("A sessão ocorrerá em 30 de outubro de 2026.")
    assert dates[0][0] == date(2026, 10, 30)


def test_ignores_invalid_dates():
    
    dates = find_dates_in_text("Prazo: 31/02/2026")
    assert dates == []


def test_parse_brl_number_with_thousands_and_cents():
    assert parse_brl_number("R$ 1.500.000,00") == 1500000.00


def test_parse_brl_number_without_cents():
    assert parse_brl_number("R$ 50.000") == 50000.0


def test_finds_money_with_currency_symbol():
    matches = find_money_in_text("O orçamento é de R$ 1.500.000,00 para o edital.")
    assert matches[0][0] == 1500000.00


def test_finds_bare_money_with_thousands_and_cents():
    matches = find_money_in_text("O valor de 1.500.000,00 foi aprovado.")
    assert matches[0][0] == 1500000.00


def test_does_not_duplicate_bare_match_inside_currency_match():
    matches = find_money_in_text("Valor: R$ 1.500.000,00")
    assert len(matches) == 1


def test_sentence_split_does_not_break_brazilian_formatted_numbers():
    # Regressão: '.' como separador de milhar não pode ser tratado como
    # fim de frase (bug real encontrado ao processar um PDF real da Petrobras).
    from parser.document_parser import _split_sentences_with_offsets

    text = "O orcamento e de R$ 1.500.000,00, conforme definido em edital."
    sentences = [s for s, _ in _split_sentences_with_offsets(text)]
    assert len(sentences) == 1
    assert "1.500.000,00" in sentences[0]


def test_law_citation_date_is_not_treated_as_deadline():
    # Regressão: uma data de promulgação de lei ("Lei nº 13.709, de 14
    # de agosto de 2018") citada na mesma frase que "inscrição" não pode
    # virar um prazo de submissão (bug real encontrado em PDF real).
    from parser.document_parser import extract_submission_deadline
    from pdf.extractor import ExtractedDocument, PageText

    text = (
        "No momento da solicitacao de inscricao, a pessoa candidata declara "
        "aceitar o tratamento de dados nos termos da Lei no 13.709, de 14 de "
        "agosto de 2018."
    )
    document = ExtractedDocument(pages=[PageText(page=1, text=text)])
    assert extract_submission_deadline(document) is None


def test_real_deadline_in_same_sentence_as_keyword_is_still_found():
    from parser.document_parser import extract_submission_deadline
    from pdf.extractor import ExtractedDocument, PageText

    text = "O prazo de inscricao encerra em 30/10/2026."
    document = ExtractedDocument(pages=[PageText(page=1, text=text)])
    result = extract_submission_deadline(document)
    assert result is not None
    from datetime import date

    assert result.value == date(2026, 10, 30)


def test_budget_has_no_naive_fallback_for_unrelated_money_value():
    # Regressão: uma taxa de inscrição ("TAXA: R$ 62,79") em uma página
    # sem nenhuma palavra-chave financeira não pode virar "orçamento"
    # (bug real: o antigo fallback pegava o primeiro valor monetário do
    # documento inteiro, sem nenhuma relação semântica).
    from parser.document_parser import extract_budget
    from pdf.extractor import ExtractedDocument, PageText

    text = "5.1 TAXA: R$ 62,79.\n5.2 A inscricao sera feita via internet."
    document = ExtractedDocument(pages=[PageText(page=1, text=text)])
    assert extract_budget(document) is None
