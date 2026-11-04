from sdd_context.tokenizer import expand_terms, tokenize


def test_ascii_identifiers_are_split_and_kept():
    tokens = tokenize("Add due_before filter to TaskHub list endpoint")
    assert "due_before" in tokens
    assert "due" in tokens
    assert "before" in tokens
    assert "taskhub" in tokens


def test_chinese_bigrams_and_domain_synonyms():
    tokens = expand_terms(tokenize("筛选截止日期，包含当天"))
    assert "筛选" in tokens
    assert "截止" in tokens
    assert "日期" in tokens
    assert "filter" in tokens
    assert "due" in tokens
    assert "date" in tokens
    assert "inclusive" in tokens


def test_empty_and_punctuation_only_input():
    assert tokenize("，。！") == []
    assert expand_terms([]) == []
