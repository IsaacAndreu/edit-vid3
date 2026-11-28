"""Settings written into .env never add lines of their own."""

import pytest


def test_dot_env_takes_no_new_lines(tmp_path):
    from pipeline import notify

    (tmp_path / ".env").write_text("A=1\n")
    for key, value in (("TELEGRAM_CHAT_ID", "1\nYOUTUBE_PROXY=http://otro"), ("TELEGRAM_CHAT_ID", "1\r2"),
                       ("X\nY", "1"), ("bad key", "1")):
        with pytest.raises(ValueError):
            notify.set_env(tmp_path, key, value)
    notify.set_env(tmp_path, "TELEGRAM_CHAT_ID", "12345")
    assert (tmp_path / ".env").read_text().splitlines() == ["A=1", "TELEGRAM_CHAT_ID=12345"]

