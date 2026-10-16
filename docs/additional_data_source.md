# Additional Data Source Proposal: Population Density & Urban Typology Metadata (SEDAC / WorldPop)

Gridded population distribution and urban footprint datasets providing population counts and density per square kilometer for global urban boundaries, such as:
    
* NASA SEDAC Gridded Population of the World
* WorldPop API 

## How can this help enrich our dataset?

Integrating population metadata enables us to calculate Human Exposure Impact, scaling air quality metrics by local population density to evaluate true public health risk rather than just atmospheric readings.

## Implementation

As demographic data changes annually rather than hourly, this requires a one-time spatial lookup per city during the geocoding phase.

Implementation involves querying the WorldPop/SEDAC dataset, adding baseline columns (population_density_sq_km) to the database schema, and writing a script to factor population weight into the dashboard's sorting and ranking views.