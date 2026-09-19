from pdf.normalizer import normalize_text


def test_collapses_multiple_spaces():
    assert normalize_text("IA    aplicada    à    saúde") == "IA aplicada à saúde"


def test_converts_crlf_to_lf():
    assert normalize_text("linha1\r\nlinha2\r\nlinha3") == "linha1\nlinha2\nlinha3"


def test_fixes_end_of_line_hyphenation():
    assert normalize_text("Inteligên-\ncia Artificial") == "Inteligência Artificial"


def test_does_not_join_list_items_incorrectly():

    text = "Lista:\n- Item um\n- Item dois"
    result = normalize_text(text)
    assert "- Item um" in result
    assert "- Item dois" in result


def test_removes_control_characters_but_keeps_newlines_and_tabs():
    text = "texto\x00com\x07controle\nnova linha\tcom tab"
    result = normalize_text(text)
    assert "\x00" not in result
    assert "\x07" not in result
    assert "\n" in result
    assert "\t" in result


def test_collapses_excessive_blank_lines():
    text = "paragrafo um\n\n\n\n\nparagrafo dois"
    result = normalize_text(text)
    assert "\n\n\n" not in result


def test_does_not_lowercase_text():
    assert "AI" in normalize_text("Utilizamos AI e LLM no projeto")


def test_empty_string_returns_empty_string():
    assert normalize_text("") == ""
