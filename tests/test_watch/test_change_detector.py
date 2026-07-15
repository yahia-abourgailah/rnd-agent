from launch_intel.watch.change_detector import ChangeDetector, hash_content


def test_hash_content_is_deterministic():
    assert hash_content("hello") == hash_content("hello")
    assert hash_content("hello") != hash_content("hello!")


def test_has_changed_true_for_unseen_url(tmp_path):
    detector = ChangeDetector(state_path=tmp_path / "state.json")
    assert detector.has_changed("https://example.com", "content") is True


def test_mark_seen_then_has_changed_false_for_same_content(tmp_path):
    detector = ChangeDetector(state_path=tmp_path / "state.json")
    detector.mark_seen("https://example.com", "content")
    assert detector.has_changed("https://example.com", "content") is False


def test_has_changed_true_after_content_changes(tmp_path):
    detector = ChangeDetector(state_path=tmp_path / "state.json")
    detector.mark_seen("https://example.com", "content v1")
    assert detector.has_changed("https://example.com", "content v2") is True


def test_state_persists_across_instances(tmp_path):
    state_path = tmp_path / "state.json"
    ChangeDetector(state_path=state_path).mark_seen("https://example.com", "content")

    reloaded = ChangeDetector(state_path=state_path)
    assert reloaded.has_changed("https://example.com", "content") is False
