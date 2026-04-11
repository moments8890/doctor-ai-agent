from domain.knowledge.persona_citations import extract_persona_citations, strip_persona_citations

def test_extract_single():
    text = "按时服药[P-ps_a1b2c3d4]，注意休息。"
    ids = extract_persona_citations(text)
    assert ids == ["ps_a1b2c3d4"]

def test_extract_multiple():
    text = "口语化[P-ps_aaaa1111]回复[P-ps_bbbb2222]。"
    ids = extract_persona_citations(text)
    assert ids == ["ps_aaaa1111", "ps_bbbb2222"]

def test_extract_empty():
    assert extract_persona_citations("普通文字没有标记") == []

def test_strip():
    text = "按时服药[P-ps_a1b2c3d4]，注意休息。"
    assert strip_persona_citations(text) == "按时服药，注意休息。"

def test_strip_multiple():
    text = "口语化[P-ps_aaaa1111]回复[P-ps_bbbb2222]完成。"
    result = strip_persona_citations(text)
    assert "[P-" not in result
    assert "口语化" in result
    assert "完成" in result

def test_strip_no_markers():
    text = "普通文字"
    assert strip_persona_citations(text) == "普通文字"

def test_does_not_strip_kb_citations():
    text = "按时服药[KB-5]，注意休息。"
    assert strip_persona_citations(text) == "按时服药[KB-5]，注意休息。"
