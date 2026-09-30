from packages.core.envfile import load_env_file


def test_env_file_values_comments_quotes_and_precedence(tmp_path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# a comment line\n"
        "CC_TEST_PLAIN=gpt-6-luna\n"
        "CC_TEST_COMMENTED=claude-sonnet-4-5   # id the server expects\n"
        'CC_TEST_QUOTED="value # kept"\n'
        "CC_TEST_URL=https://example.org/v1\n"
        "CC_TEST_EMPTY=\n"
        "CC_TEST_PRESET=from-file\n"
    )
    for name in ("PLAIN", "COMMENTED", "QUOTED", "URL", "EMPTY"):
        monkeypatch.delenv(f"CC_TEST_{name}", raising=False)
    monkeypatch.setenv("CC_TEST_PRESET", "from-environment")
    load_env_file(env)
    import os

    assert os.environ["CC_TEST_PLAIN"] == "gpt-6-luna"
    assert os.environ["CC_TEST_COMMENTED"] == "claude-sonnet-4-5"
    assert os.environ["CC_TEST_QUOTED"] == "value # kept"
    assert os.environ["CC_TEST_URL"] == "https://example.org/v1"
    assert "CC_TEST_EMPTY" not in os.environ
    assert os.environ["CC_TEST_PRESET"] == "from-environment"
    for name in ("PLAIN", "COMMENTED", "QUOTED", "URL"):
        monkeypatch.delenv(f"CC_TEST_{name}")
