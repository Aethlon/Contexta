import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "clients" / "python"))

from unittest.mock import MagicMock
from contexta_client.client import Contexta


def test_python_client_advanced_methods():
    client = Contexta(api_key="mk_live_test123")
    client._http._request = MagicMock()

    # 1. Test get_many
    client._http._request.return_value = {"count": 2, "memories": [{"id": "m1"}, {"id": "m2"}]}
    res = client.get_many(["m1", "m2"])
    assert len(res) == 2
    client._http._request.assert_called_with(
        method="POST",
        endpoint="/memories/batch-get",
        body={"memory_ids": ["m1", "m2"]},
    )

    # 2. Test retrieve_batch
    client._http._request.return_value = {"count": 1, "batch_results": [{"query": "q1", "results": []}]}
    res = client.retrieve_batch([{"query_text": "q1"}])
    assert len(res) == 1
    client._http._request.assert_called_with(
        method="POST",
        endpoint="/retrieve/batch",
        body={"queries": [{"query_text": "q1"}]},
    )

    # 3. Test feedback
    client._http._request.return_value = {"status": "success", "memory_id": "m1", "utility_score": 0.8}
    res = client.feedback("m1", signal="positive", user_correction="Correction", penalty=0.2)
    assert res["status"] == "success"
    client._http._request.assert_called_with(
        method="POST",
        endpoint="/memories/m1/feedback",
        body={"signal": "positive", "penalty": 0.2, "user_correction": "Correction"},
        is_write=True,
    )

    # 4. Test add_rule
    client.observe = MagicMock(return_value={"status": "accepted"})
    res = client.add_rule(user_id="u1", rule="Always write docstrings", title="Documentation Rule")
    assert res == {"status": "accepted"}
    client.observe.assert_called_once()
    call_kwargs = client.observe.call_args.kwargs
    assert call_kwargs["user_id"] == "u1"
    assert call_kwargs["metadata"]["memory_type"] == "procedural"
    assert "rule" in call_kwargs["metadata"]["tags"]
    assert "procedural" in call_kwargs["metadata"]["tags"]

    # 5. Test investigate
    client._http._request.return_value = {"status": "success", "query": "What stack?", "results": []}
    res = client.investigate("What stack?", user_id="u1", max_hops=3)
    assert res["status"] == "success"
    client._http._request.assert_called_with(
        method="POST",
        endpoint="/retrieve/investigate",
        body={"query_text": "What stack?", "user_id": "u1", "max_hops": 3, "limit": 15},
    )

    # 6. Test reflect
    client._http._request.return_value = {"status": "success", "contradictions_resolved": 2}
    res = client.reflect(user_id="u1", apply_supersession=True)
    assert res["contradictions_resolved"] == 2
    client._http._request.assert_called_with(
        method="POST",
        endpoint="/memories/reflect",
        body={"user_id": "u1", "apply_supersession": True, "min_occurrences_for_pattern": 3},
        is_write=True,
    )

