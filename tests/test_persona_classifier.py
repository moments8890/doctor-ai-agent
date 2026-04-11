from domain.knowledge.persona_classifier import compute_pattern_hash

def test_pattern_hash_deterministic():
    h1 = compute_pattern_hash("reply_style", "偏好口语化")
    h2 = compute_pattern_hash("reply_style", "偏好口语化")
    assert h1 == h2

def test_pattern_hash_different_fields():
    h1 = compute_pattern_hash("reply_style", "偏好口语化")
    h2 = compute_pattern_hash("avoid", "偏好口语化")
    assert h1 != h2

def test_pattern_hash_case_insensitive():
    h1 = compute_pattern_hash("reply_style", "Test Summary")
    h2 = compute_pattern_hash("reply_style", "test summary")
    assert h1 == h2

def test_pattern_hash_length():
    h = compute_pattern_hash("reply_style", "test")
    assert len(h) == 16
