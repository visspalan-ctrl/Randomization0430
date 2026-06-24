from app.state import generate_trial_assignments, trial_group_at_index


def test_generate_trial_assignments_is_deterministic():
    a = generate_trial_assignments(8, (4, 8, 12), 4300430)
    b = generate_trial_assignments(8, (4, 8, 12), 4300430)
    assert a == b
    assert len(a) == 8
    assert all(g in {"GENAI", "HUMAN"} for g in a)


def test_block_balance_within_each_generated_block():
    seq = generate_trial_assignments(24, (4,), 12345)
    for i in range(0, len(seq), 4):
        chunk = seq[i : i + 4]
        assert chunk.count("GENAI") == chunk.count("HUMAN")


def test_trial_group_at_index_matches_prefix_of_sequence():
    seed = 999
    sizes = (4,)
    for index in range(6):
        assert trial_group_at_index(index, sizes, seed) == generate_trial_assignments(index + 1, sizes, seed)[index]
