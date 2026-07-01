from health_advisor.glossary import load_glossary


def test_longest_term_wins_over_substring():
    g = load_glossary()
    hits = dict(g.find("track my HOMA-IR"))
    assert "HOMA-IR" in hits
    assert "IR" not in hits  # not double-counted inside HOMA-IR


def test_word_boundary_no_false_positive():
    g = load_glossary()
    # "stairs" must not trip the IR term
    assert g.find("I climbed the stairs") == []


def test_expands_known_shorthand():
    g = load_glossary()
    hits = dict(g.find("what goes in my D&G and SMASH rotation"))
    assert "D&G" in hits
    assert "SMASH" in hits


def test_annotate_appends_note():
    g = load_glossary()
    out = g.annotate("dose of MB")
    assert "[shorthand:" in out
    assert "methylene blue" in out


def test_annotate_noop_without_terms():
    g = load_glossary()
    assert g.annotate("plain english sentence") == "plain english sentence"
