from backend.graph.parse import flagged_vertex, vertices


def test_flagged_vertex_fills_attributes_from_history_when_t_is_only_an_id() -> None:
    payload = [
        {"t": "3514030"},
        {
            "history": [
                {
                    "v_id": "3514030",
                    "v_type": "CardTransaction",
                    "attributes": {
                        "ts": "2016-12-04 19:55:28",
                        "amount": 77.07,
                        "product_cd": "W",
                        "channel": "in_person",
                        "billing_region": "444.0",
                        "billing_country": "87.0",
                        "risk_score": 0.61,
                    },
                }
            ]
        },
    ]
    flagged = flagged_vertex(payload)
    assert flagged["v_id"] == "3514030"
    assert flagged["attributes"]["amount"] == 77.07
    assert flagged["attributes"]["billing_region"] == "444.0"


def test_vertices_keeps_empty_attributes() -> None:
    payload = [{"c": [{"v_id": "HHG-999", "v_type": "InvestigationCase", "attributes": {}}]}]
    assert vertices(payload, "c")[0]["attributes"] == {}


def test_flagged_vertex_fills_attributes_from_history_when_t_is_only_an_id() -> None:
    payload = [
        {"t": "3514030"},
        {
            "history": [
                {
                    "v_id": "3514030",
                    "v_type": "CardTransaction",
                    "attributes": {
                        "ts": "2016-12-04 19:55:28",
                        "amount": 77.07,
                        "product_cd": "W",
                        "channel": "in_person",
                        "billing_region": "444.0",
                        "billing_country": "87.0",
                        "risk_score": 0.61,
                    },
                }
            ]
        },
    ]
    flagged = flagged_vertex(payload)
    assert flagged["v_id"] == "3514030"
    assert flagged["attributes"]["amount"] == 77.07
    assert flagged["attributes"]["billing_region"] == "444.0"
