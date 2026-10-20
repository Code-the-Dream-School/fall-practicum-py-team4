# Dataset choice and product summary

## Description

**Objective:**

Write a short summary in your team's own words that explains:

- the dataset the team selected and why
- the question or problem the product is intended to answer
- the data the product needs
- what the extract, transform, and load stages will do
- how the prepared data will eventually support the dashboard

**Acceptance criteria:**

- Primary dataset/data source is selected and documented.
- Source URL/API documentation is included.
- Dataset purpose and key fields are briefly described.
- Reason for selecting the dataset is documented.
- Product/project use case is clearly summarized.
- Documentation is added to the project repository.

## Initial Data Set:

**[Air Pollution](https://openweathermap.org/api/air-pollution?collection=environmental)**

- [Current End Point](https://openweathermap.org/api/air-pollution#current)
- [Historical End Point](https://openweathermap.org/api/air-pollution#history)
- [Forecast End Point](https://openweathermap.org/api/air-pollution#forecast)

These end points and datasets were chosen to give insight on the issue of air pollution across different locations worldwide through a general air quality dashboard.

An additional geographic data source may be needed to obtain latitude and longitude coordinates, as the API requires these parameters.

Contains: current, historical, and forecasted pollution

**Available measurements:**

- AQI: Air quality index on a 1 to 5 scale (5 being the worst) ([Index levels for specific areas](https://openweathermap.org/api/air-pollution-index-levels?collection=environmental))
- PM2.5: Fine particulate matter
- PM10: Coarse particulate matter
- CO: Carbon monoxide
- NO: Nitrogen monoxide
- NO₂: Nitrogen dioxide
- O₃: Ozone
- SO₂: Sulfur dioxide
- NH₃: Ammonia
- Time stamps and coordinates

## Pipeline Stages:

**(Needs to be done once per location)**

**Extract 1:** Pull long and lat for parameters including context, date pulled, parameters, and source payload.

**Transform 1:** Validate entries for completeness, add geographic information such as state or country.

**Load 1:** Store features and geographic data for reuse.

**(Can be done multiple times at set times or real time)**

**Extract 2:** Pull data from each required endpoint including context, date pulled, parameters, and source payload.

**Transform 2:** Validate entries for completeness, null checks, geographic granularity, and any analytical aggregations or new features needed for the dashboard.

**Load 2:** Store features and data according to the team's data contracts. Must be idempotent due to repeated pulls in the future.

## Project:

The data will support the following project:

- **Air quality dashboard**
  - Provides an understanding of pollution levels worldwide for a user-selected ZIP code or geographic coordinates (longitude and latitude).
  - Displays selected air pollution indicators using current, historical, and/or forecasted data.
  - Need to choose aggregation level like hours or day then the key indicators.
  - Geographic coordinates will be used to retrieve pollution measurements for the selected location.
  - Streamlit will be used to develop the interactive dashboard.
