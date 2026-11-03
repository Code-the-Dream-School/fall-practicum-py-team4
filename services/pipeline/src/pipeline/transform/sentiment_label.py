def aqi_to_sentiment(aqi: int) -> str:
    sentiments = {
        1: "Good",
        2: "Fair",
        3: "Moderate",
        4: "Poor",
        5: "Very Poor"
    }

    return sentiments[aqi]