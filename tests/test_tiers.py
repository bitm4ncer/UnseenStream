from app import tiers


def test_cold_channel_with_hit_becomes_warm():
    tier, streak, idle = tiers.apply_poll_result("cold", 1, 0, 5)
    assert (tier, streak, idle) == ("warm", 1, 0)


def test_warm_channel_promotes_after_two_hits():
    tier, streak, idle = tiers.apply_poll_result("warm", 1, 1, 0)
    assert (tier, streak, idle) == ("hot", 2, 0)


def test_hot_channel_demotes_after_six_empty_polls():
    tier, streak, idle = tiers.apply_poll_result("hot", 0, 3, 5)
    assert (tier, streak, idle) == ("warm", 0, 6)


def test_warm_channel_demotes_after_twenty_empty_polls():
    tier, streak, idle = tiers.apply_poll_result("warm", 0, 0, 19)
    assert (tier, streak, idle) == ("cold", 0, 20)


def test_hot_stays_hot_while_hits_continue():
    tier, streak, idle = tiers.apply_poll_result("hot", 2, 4, 0)
    assert tier == "hot"
    assert idle == 0


def test_backoff_grows_and_is_capped():
    assert tiers.backoff_seconds(1) == 60
    assert tiers.backoff_seconds(2) == 120
    assert tiers.backoff_seconds(4) == 480
    assert tiers.backoff_seconds(20) == 3600


def test_dead_after_five_failures():
    assert tiers.is_dead(4) is False
    assert tiers.is_dead(5) is True


def test_cap_targets():
    assert tiers.next_tier_on_cap("hot") == "warm"
    assert tiers.next_tier_on_cap("warm") == "cold"
    assert tiers.next_tier_on_cap("cold") is None
