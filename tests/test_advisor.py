from health_advisor.advisor import Advisor
from health_advisor.drive_io import encode_b64

FILE_BODIES = {
    "1Acbu3DMnRtTC-OUA2cQQ1zwISK1sbrzL": "# Health_Stack_MASTER\nmorning greens drink ...",
    "1ovGfVPL8OW0GdOeoRAuJKE8asR3gDlGY": "# Health_References\nDr. Boz ...",
    "1U2Z9Nb7Gm35LiRYzD8qbN5ApQ-jpizHe": "# IR stack map\nfasting insulin < 6 ...",
}


class FakeClient:
    def __init__(self, bodies):
        self.bodies = bodies

    def download_b64(self, file_id):
        return encode_b64(self.bodies[file_id])

    def create_file(self, **kwargs):  # not used here
        return "NEW"


def test_prepare_loads_grounding_and_flags():
    adv = Advisor(FakeClient(FILE_BODIES))
    ctx = adv.prepare("what's my target fasting insulin", topic="insulin")
    assert ctx.grounded
    titles = ctx.source_titles()
    assert "Health_Stack_MASTER.md" in titles
    assert "Health_References.md" in titles
    assert "Insulin_Resistance_Stack_Map.md" in titles
    # guardrail fired on the optimal range
    assert any(f.kind == "optimal-vs-standard" for f in ctx.flags)


def test_prepare_expands_shorthand():
    adv = Advisor(FakeClient(FILE_BODIES))
    ctx = adv.prepare("is my HOMA-IR good", topic="ir")
    assert "insulin-resistance index" in ctx.normalized_query
