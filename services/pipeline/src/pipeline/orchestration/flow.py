import time
from prefect import flow, get_run_logger
from pipeline.utils.track_runs import log_flow_success, log_flow_failure
from pipeline.orchestration.tasks import (
    generate_execution_plan,
    check_geocoding_cache,
    fetch_geocoding,
    fetch_air_pollution,
    load_raw_cities_task,
    load_raw_air_pollution_task,
    transform_city,
    transform_air,
    transform_rolling_averages
)


# --- PHASE 1: Core Data ETL Flow ---
# this name has to match on the planner
@flow(name="City Air Tracker ETL", log_prints=True, on_completion=[log_flow_success], on_failure=[log_flow_failure])
def main_etl_flow(cities: list[str] = None):
    """Main orchestration flow handling multiple cities."""

    if cities is None:
        cities = ['New York']

    logger = get_run_logger()
    logger.info(f"Starting ETL Pipeline for {len(cities)} cities")

    # Define execution plan (Backfilling, Incremental Extraction)
    execution_plan = generate_execution_plan(cities)
    
    if not execution_plan:
        logger.info("No missing data found across any cities. Pipeline up to date!")
        return

    logger.info(f"Execution plan generated for {len(execution_plan)} target items.")

    # Iterate over execution plan
    for item in execution_plan:
        city_name = item["city_name"]
        city_id = item["city_id"]
        missing_dates = item["missing_dates"]
        
        logger.info(f"Processing city: {city_name} with {len(missing_dates)} missing dates.")

        try:
            # Get Geocoding (Cache or OpenMeteo API)
            cached_data = check_geocoding_cache(city_name)
            
            if cached_data:
                logger.info(f"Found cache geocoding data for {city_name}")
                location_data = cached_data
                logger.info(f"Coordinates for {city_name} fetched from cache")
            else:
                logger.info(f"No cache found. Fetching geocoding from OpenMeteo for {city_name}")
                location_data = fetch_geocoding(city_name)
                load_raw_cities_task(location_data)

                logger.info(f"Coordinates for {city_name} saved to cities_raw")
                # Saved fetched data to gold_cities
                transform_city(location_data)
                logger.info(f"Coordinates for {city_name} saved to gold_cities")

                # Re-query the cache so we have the city_id in hand
                cached_data = check_geocoding_cache(city_name)

            city_id = cached_data.get("city_id")
            lat = cached_data.get("latitude")
            lon = cached_data.get("longitude")
            
            # Loop through the missing dates to extract air pollution for each date
            for target_date in missing_dates:
                logger.info(f"Fetching air pollution for {city_name} on date: {target_date}...")
                
                pollution_data = fetch_air_pollution(city=city_name, lat=lat, lon=lon, date=target_date)

                if pollution_data:
                    logger.info(f"Succesfully fetched air pollution for {city_name} on date: {target_date}...")

                    load_raw_air_pollution_task(pollution_data)
                    logger.info(f"Saved raw data for {city_name} on date: {target_date}...")

                    air_count, formatted_gold = transform_air(pollution_data, city_id)
                    logger.info(f"Formatted {air_count} air records for {city_name} on date: {target_date}...")

                    rolling_count, rolling_7d_added = transform_rolling_averages(city_id, formatted_gold, ['aqi', 'pm2_5'], city_name)
                    logger.info(f"Added 7d rolling average for {rolling_count} records for {city_name} on date: {target_date}...")

                    #load_gold(rolling_7d_added)

                    
            logger.info(f"Successfully processed all missing dates for {city_name}")
            
        except Exception as e:
            logger.error(f"Failed to process pipeline for {city_name}: {e}")
            continue
        
    logger.info("Phase 1 ETL execution completed successfully!")


# --- PHASE 2: LLM Enrichment Flow --
# @flow(
#     name="City Air Tracker LLM Enrichment", 
#     log_prints=True, 
#     on_completion=[log_flow_success], 
#     on_failure=[log_flow_failure]
# )
# def llm_enrichment_flow():
#     """Phase 2: Scans for un-enriched rows (NULL llm_response), batches them, and calls LLM."""
#     logger = get_run_logger()
#     logger.info("Starting Phase 2 LLM Enrichment Worker Flow")
    
#     try:
#         # Calls your paginated worker task that scans nulls, aggregates by date, and updates DB
#         run_llm_enrichment()
#         logger.info("Phase 2 LLM Enrichment completed successfully!")
#     except Exception as e:
#         logger.error(f"LLM Enrichment flow failed: {e}")
#         raise e

    
if __name__ == "__main__":
    main_etl_flow()