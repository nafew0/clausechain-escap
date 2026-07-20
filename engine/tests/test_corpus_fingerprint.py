from packages.core.corpus_fingerprint import corpus_fingerprint


def test_corpus_fingerprint_is_order_independent_and_content_sensitive():
    one = {"provision_id": "p1", "text": "exact text",
           "props": {"law_name": "Act", "article_section": "s. 1",
                     "content_sha256": "source-a"}}
    two = {"provision_id": "p2", "text": "other text",
           "props": {"law_name": "Act", "article_section": "s. 2",
                     "content_sha256": "source-a"}}
    assert corpus_fingerprint([one, two]) == corpus_fingerprint([two, one])
    changed = {**one, "text": "changed text"}
    assert corpus_fingerprint([one, two]) != corpus_fingerprint([changed, two])
