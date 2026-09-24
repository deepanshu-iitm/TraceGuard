from backend.retrieve.vectors import VECTOR_DIM, embed_text


def test_embed_text_is_32_dim_and_normalized() -> None:
    vec = embed_text("verify customer step up auth new device")
    assert len(vec) == VECTOR_DIM
    assert abs(sum(value * value for value in vec) - 1.0) < 1e-6


def test_embed_text_is_deterministic() -> None:
    assert embed_text("card testing") == embed_text("card testing")
    assert embed_text("card testing") != embed_text("account takeover")


def test_vertex_id_roundtrip() -> None:
    from backend.retrieve.vectors import doc_id_from_vertex, vertex_id

    assert vertex_id("policy:R1") == "policy_R1"
    assert doc_id_from_vertex("policy_R1") == "policy:R1"
    assert doc_id_from_vertex(vertex_id("closed_case/CC-1066")) == "closed_case/CC-1066"
