

def test_analysed_options_runs_on_its_own(tmp_path):
    """gta5: `official` was pick_moments' local name, read in analysed_options → NameError at coldopen."""
    from pipeline import coldopen
    from pipeline.context import RunContext

    ctx = RunContext.create("t", root=tmp_path, config={"content": {"official_channels": ["Rockstar Games"]}})
    assert coldopen.analysed_options(ctx, [], [], set(), None, set()) == []


def test_a_photo_of_the_protagonist_is_a_valid_fallback():
    from pipeline.schemas import FallbackItem

    assert "protagonist-photo" in FallbackItem.model_fields["method"].annotation.__args__
