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

**Air Pollution**

- Current End Point
- Historical End Point
- Forecast End Point

These end points and datasets were chosen to give insight on the issue of air pollution in (Our selected scope and area).

Could possibly need another API or list of geo long and lat data due to the API requiring these as parameters.

Contains: current, historical, and forecasted pollution

**Available measurements:**

- AQI: Air quality index on a 1 to 5 scale(5 being the worse)(Index levels for specific areas)
- PM2.5: Fine particulate matter
- PM10: Coarse particulate matter
- CO: Carbon monoxide
- NO: Nitrogen monoxide
- NO_2: Nitrogen dioxide
- O_2: Ozone
- SO_2: Sulfur dioxide
- NH_2: Ammonia
- Time stamps and coordinates

## Pipeline Stages:

**(Needs to be done once)**

**Extract 1:** Pull long and lat for parameters including context, date pulled, parameters, and source payload.

**Transform 1:** Validate entries for completeness(need to discuss handling of failure of this constraint), add geographic information such as state or country.

**Load 1:** Store features and data(need to discuss data storage location)

**(Can be done multiple times at set times or real time)**

**Extract 2:** Pull data from each required endpoint including context, date pulled, parameters, and source payload.

**Transform 2:** Validate entries for completeness, null checks, geographic granularity, any analytical aggregations or new features to be created(depends on project chosen and analysis to be done/visualized).

**Load 2:** Store features and data(need to discuss data storage location) must be idempotent due to repeated pulls in the future.

## Possible Projects:

The data will support these(this) (possible) project(s):

- **Air quality dashboard**
  - Provides an understanding of pollution levels in a selected country, state, or city through selected indicators and historical/current rates comparisons.
  - Could use either or all end points
  - Need to choose aggregation level like hours or day then the key indicators
  - Which coordinates or how many coordinate(long, lat) will be used for this(need to check this)
  - We could use streamlit or other dashboard services such as powerBI or tableau
- **GIS**
  - Provides holistic visual of areas of concern or no concern
  - Can change color based on current to different forecast horizons
  - Color coded by AQI map of a selected country, region, state, or world
  - Drill down from a specific continent to country to state or region
  - Tooltips describing key metrics for each level of drill down through click or zoom
  - Can show on the side current warning areas or forecasted warning areas with level of warning

Combination of these two are also possible
