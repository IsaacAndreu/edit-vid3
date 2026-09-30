from pipeline.config import PROJECT_ROOT
from pipeline.context import RunContext
from pipeline.package import CONCEPT_SYSTEM, color_name


def test_brand_colours_become_words_for_the_image_model():
    assert color_name("#19fe5b") == "lime green"
    assert color_name("#ffd400") == "yellow"
    assert color_name("#a855f7") == "purple"
    assert color_name("#ff3b30") == "red"
    assert color_name("#f5f5f5") == "white"


def test_business_channel_uses_concept_thumbnails():
    assert RunContext.create("Video1", root=PROJECT_ROOT).section("package")["thumbnail_style"] == "concept"
    assert RunContext.create("_t", root=PROJECT_ROOT, channel="gimnasia").section("package").get("thumbnail_style", "frame") == "frame"
    assert '"concepts"' in CONCEPT_SYSTEM and "sin caras" in CONCEPT_SYSTEM
