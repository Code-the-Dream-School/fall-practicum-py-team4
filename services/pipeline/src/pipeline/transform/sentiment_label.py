def aqi_to_sentiment(aqi: int) -> str:
    sentiments = {
        1: "Good",
        2: "Fair",
        3: "Moderate",
        4: "Poor",
        5: "Very Poor"
    }

    if type(aqi) is not int or aqi not in sentiments:
        raise ValueError("AQI must be an integer between 1 and 5.")

    return sentiments[aqi]