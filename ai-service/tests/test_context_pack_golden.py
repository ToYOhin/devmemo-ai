import json

import pytest

from app.domain.context_pack import ContextPackRequest
from app.services.context_pack import build_context_pack
from tests.context_pack_fixture import context_pack_inputs, load_context_pack_fixture


@pytest.mark.parametrize("case_name", ["accepted_sorted", "max_items"])
def test_context_pack_golden_output_matches_shared_fixture(case_name):
    fixture = load_context_pack_fixture()
    case = fixture["golden_cases"][case_name]
    memos, insights = context_pack_inputs()

    response = build_context_pack(ContextPackRequest(**case["request"]), memos, insights)

    assert response.markdown == case["expected"]["markdown"]
    assert response.to_dict() == case["expected"]["json"]
    assert response.to_json() == json.dumps(
        case["expected"]["json"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    assert "Pending fact" not in response.markdown
