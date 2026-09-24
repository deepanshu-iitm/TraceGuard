"""Write GSQL that inserts policy/pattern/regulatory RagDocument embeddings."""

from pathlib import Path

from backend.retrieve.corpus import PATTERN_DOCS, POLICY_DOCS, REGULATORY_DOCS
from backend.retrieve.vectors import _doc_kind, embed_text, vertex_id

OUT = Path(__file__).resolve().parents[2] / "tigergraph" / "loading" / "seed_rag_documents.gsql"


def _gsql_str(value: str) -> str:
    cleaned = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
    return f'"{cleaned}"'


def main() -> None:
    docs = list(POLICY_DOCS) + list(PATTERN_DOCS) + list(REGULATORY_DOCS)
    inserts = ["  SumAccum<INT> @@n;"]
    runs: list[str] = []
    for doc in docs:
        text = doc.text[:8000]
        kind = _doc_kind(doc.doc_id)
        vid = vertex_id(doc.doc_id)
        vec = embed_text(f"{doc.title} {text} {doc.pattern}")
        floats = ", ".join(f"{value:.8f}" for value in vec)
        inserts.append(
            "  INSERT INTO RagDocument VALUES ("
            f"{_gsql_str(vid)}, {_gsql_str(doc.title[:200])}, "
            f"{_gsql_str(text)}, {_gsql_str(kind)});"
        )
        inserts.append("  @@n += 1;")
        runs.append(f"RUN QUERY seed_rag_emb({_gsql_str(vid)}, [{floats}])")
    query = (
        "USE GRAPH FraudGraph\n\n"
        "DROP QUERY seed_rag_insert\n"
        "DROP QUERY seed_rag_embeddings\n"
        "DROP QUERY seed_rag_emb\n\n"
        "CREATE QUERY seed_rag_insert() FOR GRAPH FraudGraph {\n"
        + "\n".join(inserts)
        + "\n  PRINT @@n;\n"
        + "}\n\nINSTALL QUERY seed_rag_insert\n"
        + "RUN QUERY seed_rag_insert()\n\n"
        "CREATE QUERY seed_rag_emb(VERTEX<RagDocument> d, LIST<FLOAT> emb) FOR GRAPH FraudGraph SYNTAX v3 {\n"
        "  start = {d};\n"
        "  updated = SELECT s FROM start:s POST-ACCUM (s) s.embedding = emb;\n"
        "  PRINT updated;\n"
        "}\n\nINSTALL QUERY seed_rag_emb\n"
        + "\n".join(runs)
        + "\nDROP QUERY seed_rag_insert\n"
        + "DROP QUERY seed_rag_emb\n"
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(query, encoding="utf-8")
    print(f"wrote {OUT} ({len(docs)} documents, {OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
