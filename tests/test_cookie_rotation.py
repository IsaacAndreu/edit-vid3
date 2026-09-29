import pytest

from pipeline.sourcing.common import SourceUnavailable
from pipeline.sourcing.youtube import YouTubeSource


def _source(tmp_path, n):
    sets = [(f"# account {i}\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tx{i}\n", tmp_path / f"a{i}.txt") for i in range(n)]
    return YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "account_switch_pause": 0},
                         cookie_sets=sets)


def test_requests_take_turns_between_accounts(tmp_path):
    yt = _source(tmp_path, 3)
    used = [yt._call("search", lambda: yt._local.account) for _ in range(6)]
    assert used == [0, 1, 2, 0, 1, 2]
    yt.close()


def test_a_blocked_account_is_set_aside_and_the_others_carry_on(tmp_path):
    yt = _source(tmp_path, 3)

    def fetch():
        if yt._local.account == 1:
            raise RuntimeError("ERROR: Sign in to confirm you're not a bot")
        return yt._local.account

    results = [yt._call("search", fetch) for _ in range(5)]
    assert 1 not in results and yt._bad == {1} and not yt.blocked


def test_blocked_everywhere_when_every_account_is_blocked(tmp_path):
    yt = _source(tmp_path, 2)

    def fetch():
        raise RuntimeError("Sign in to confirm you're not a bot")

    with pytest.raises(SourceUnavailable):
        yt._call("search", fetch)
    assert yt._bad == {0, 1} and "2 cuentas" in yt.blocked


def test_without_cookies_a_block_stops_youtube(tmp_path):
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0})
    with pytest.raises(SourceUnavailable):
        yt._call("search", lambda: (_ for _ in ()).throw(RuntimeError("not a bot")))
