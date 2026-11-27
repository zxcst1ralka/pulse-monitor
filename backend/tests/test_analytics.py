from app.services.analytics import uptime


def test_uptime_counts_only_completed_checks():
    assert uptime(0, 0) is None
    assert uptime(0, 3) == 0
    assert uptime(2, 3) == 66.67
    assert uptime(3, 3) == 100
