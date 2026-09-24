from backend.graph.parse import flagged_vertex


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
