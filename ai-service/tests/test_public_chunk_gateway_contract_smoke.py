from scripts.public_chunk_gateway_contract_smoke import run_gateway_contract_smoke


def test_gateway_contract_smoke_covers_the_controlled_rollout_boundary():
    assert run_gateway_contract_smoke() == {
        "disabled": 503,
        "missing_signature": 401,
        "tampered_body": 401,
        "ambiguous_scope": 422,
        "degraded_store": 503,
        "authorized_redacted_deduplicated": 200,
    }
