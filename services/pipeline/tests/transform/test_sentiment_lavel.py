import pytest
from src.pipeline.transform.sentiment_label import aqi_to_sentiment


@pytest.mark.parametrize("aqi, expected", [
    (1, "Good"),
    (2, "Fair"),
    (3, "Moderate"),
    (4, "Poor"),
    (5, "Very Poor"),
])
def test_valid_aqi(aqi, expected):
    result = aqi_to_sentiment(aqi)

    assert result == expected
    assert isinstance(result, str)


@pytest.mark.parametrize("aqi", [0, 6, -1, 100])
def test_invalid_aqi(aqi):
    with pytest.raises(KeyError):
        aqi_to_sentiment(aqi)


def test_none_aqi():
    with pytest.raises(KeyError):
        aqi_to_sentiment(None)
