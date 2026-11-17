from tender_radar.textmatch import KeywordMatcher, compile_term, ua_stem


def found(term: str, text: str) -> bool:
    return bool(compile_term(term).search(text))


def test_stem_strips_one_ending_but_keeps_four_letters():
    assert ua_stem("розробка") == "розробк"
    assert ua_stem("сайт") == "сайт"


def test_ukrainian_inflections_match():
    assert found("розробка", "Послуги з розробки програм")
    assert found("розробка", "замовлення на розробку")
    assert found("програмне забезпечення", "супровід програмного забезпечення")


def test_o_i_alternation():
    assert found("простір", "оренда простору")


def test_word_boundaries():
    assert not found("сайт", "рекламний вісайтинг")  # inside another word
    assert found("сайт", "створення сайту")


def test_english_terms_allow_short_suffix():
    assert found("website", "Two Websites for the city")
    assert not found("cloud", "cloudiness of the sky")


def test_abbreviations_are_case_sensitive_whole_words():
    assert found("CRM", "впровадження CRM-системи")
    assert not found("CRM", "crm lowercase is ignored")
    assert not found("API", "capital")


def test_matcher_reports_groups_and_terms():
    matcher = KeywordMatcher({"Web": ("веб-сайт",), "Security": ("кібербезпека",)})
    result = matcher.match("Створення веб-сайту з кібербезпекою")
    assert result.groups == ["Web", "Security"]
    assert result.terms == ["веб-сайт", "кібербезпека"]
    assert matcher.match("Закупівля паперу").groups == []
