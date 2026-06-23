from health_advisor.guardrails import guardrail_flags


def _kinds(flags):
    return {f.kind for f in flags}


def test_mb_triggers_safety_and_loop():
    flags = guardrail_flags("what's my methylene blue dose")
    kinds = _kinds(flags)
    assert "mb-safety" in kinds
    assert "medical-loop" in kinds
    text = " ".join(f.message for f in flags)
    assert "MAOI" in text
    assert "G6PD" in text
    assert "5x" in text or "5x)" in text  # the same-scale-number trap


def test_mb_abbreviation_triggers():
    assert "mb-safety" in _kinds(guardrail_flags("MB once daily?"))


def test_optimal_vs_standard_for_fasting_insulin():
    flags = guardrail_flags("what's the target for fasting insulin")
    assert "optimal-vs-standard" in _kinds(flags)
    assert any("< 6" in f.message for f in flags)


def test_homa_ir_optimal_flag():
    flags = guardrail_flags("is my HOMA-IR ok")
    assert any("1.0" in f.message for f in flags if f.kind == "optimal-vs-standard")


def test_medical_loop_on_statin():
    assert "medical-loop" in _kinds(guardrail_flags("should I start atorvastatin"))


def test_plain_question_no_flags():
    assert guardrail_flags("what's in the morning greens drink") == []


def test_no_duplicate_flags():
    flags = guardrail_flags("methylene blue methylene blue")
    msgs = [(f.kind, f.message) for f in flags]
    assert len(msgs) == len(set(msgs))
