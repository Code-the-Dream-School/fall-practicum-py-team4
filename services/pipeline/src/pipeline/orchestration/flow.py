import time
from typing import Any
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
    fetch_historical,
    calculate_rolling_averages,
    load_gold_cities_task,
    load_gold_air_data_task,
    # llm_enrichment_task
)


# --- PHASE 1: Core Data ETL Flow ---
@flow(name="City Air Tracker ETL", log_prints=True, on_completion=[log_flow_success], on_failure=[log_flow_failure])
def main_etl_flow(
    cities: list[str] | None = None,
    mode: str = "incremental",
    ):
    """Main orchestration flow handling multiple cities."""

    if cities is None:
        cities = ['New York']

    logger = get_run_logger()
    current_stage = "INITIALIZATION"

    result_summary: dict[str, Any] = {
        "status": "RUNNING",
        "mode": mode,
        "cities": cities,
        "counts": {
            "extract_geocoding": 0,
            "extract_pollution_days": 0,
            "load_raw_cities": 0,
            "load_raw_pollution_batches": 0,
            "transform_cities": 0,
            "transform_air_records": 0,
            "transform_rolling_records": 0,
            "load_gold_cities": 0,
            "load_gold_air_records": 0,
            "enriched_records": 0,
        },
        "failed_stage": None,
        "error": None,
        "succeeded_cities": [],
        "failed_cities": [],
    }

    logger.info(f"[RUN START] Starting ETL Pipeline for {len(cities)} cities, mode: {mode}")

    # --- STAGE 0: PLANNING ---
    current_stage = "PLANNING"

    try:
        logger.info(f"[STAGE START: {current_stage}] Defining Execution plan")
        execution_plan = generate_execution_plan(cities, mode)
    except Exception as e:
        result_summary["status"] = "FAILED"
        result_summary["failed_stage"] = current_stage
        result_summary["error"] = f"{type(e).__name__}: {e}"
        logger.exception(f"[STAGE FAILED: {current_stage}] Failed to generate execution plan: {e}")
        raise
    
    if not execution_plan:
        logger.info(f"[STAGE SUCCESS: {current_stage}] No missing data found. Pipeline up to date.")
        result_summary["status"] = "NO_OP"
        logger.info(f"[RUN SUCCESS] Completed with result_summary: {result_summary}")
        return result_summary

    logger.info(f"[STAGE SUCCESS: {current_stage}] Execution plan generated for {len(execution_plan)} target items.")

    # --- STAGES 1-3: EXTRACT, LOAD, TRANSFORM (Per City) ---
    for item in execution_plan:
        city_name = item["city_name"]
        city_id = item["city_id"]
        missing_dates = item["missing_dates"]
        
        logger.info(f"Processing city: {city_name} with {len(missing_dates)} missing dates.")

        try:
            # 1A. Geocoding Extract / Load / Transform
            current_stage = "EXTRACT_GEOCODING"
            cached_data = check_geocoding_cache(city_name) 

            if cached_data:
                logger.info(f"[{current_stage}] Found cache geocoding data for {city_name}")
            else:
                logger.info(f"[STAGE START: {current_stage}] Fetching geocoding from OpenMeteo for {city_name}")
                city_data = fetch_geocoding(city_name)
                result_summary["counts"]["extract_geocoding"] += 1

                current_stage = "LOAD_RAW_CITIES"
                logger.info(f"[STAGE START: {current_stage}] Loading raw geocoding for {city_name}")
                load_raw_cities_task(city_data)
                result_summary["counts"]["load_raw_cities"] += 1

                current_stage = "TRANSFORM_CITY"
                logger.info(f"[STAGE START: {current_stage}] Transforming data for {city_name}...")
                gold_city_count, gold_city_data = transform_city(city_data)
                result_summary["counts"]["transform_cities"] += gold_city_count

                current_stage = "LOAD_GOLD_CITIES"
                logger.info(f"[STAGE START: {current_stage}] Saving golden data for {city_name} on gold_cities")
                load_gold_cities_task(gold_city_data)
                result_summary["counts"]["load_gold_cities"] += 1

                current_stage = "RECHECK_GEOCODING_CACHE"
                # Re-query the cache so we have the city_id in hand
                cached_data = check_geocoding_cache(city_name)
                if not cached_data:
                    raise RuntimeError(f"Geocoding cache still empty for '{city_name}' after gold load.")

            city_id = cached_data.get("city_id")
            lat = cached_data.get("latitude")
            lon = cached_data.get("longitude")
            
            # 1B. Air Pollution Extract -> Load Raw -> Transform -> Load Gold
            for target_date in missing_dates:
                current_stage = f"EXTRACT_AIR_POLLUTION ({city_name} @ {target_date})"
                logger.info(f"[STAGE START: {current_stage}] Fetching air pollution data")                
                pollution_data = fetch_air_pollution(city=city_name, lat=lat, lon=lon, date=target_date)

                if not pollution_data:
                    raise ValueError(f"Empty air pollution payload returned for {city_name} on {target_date}")
                result_summary["counts"]["extract_pollution_days"] += 1

                current_stage = f"LOAD_RAW_AIR_POLLUTION ({city_name} @ {target_date})"
                logger.info(f"[STAGE START: {current_stage}] Saving raw air pollution data")
                load_raw_air_pollution_task(pollution_data)
                result_summary["counts"]["load_raw_pollution_batches"] += 1

                current_stage = f"TRANSFORM_AIR_POLLUTION ({city_name} @ {target_date})"
                logger.info(f"[STAGE START: {current_stage}] Transforming air records and 7d rolling averages")
                air_count, formatted_gold = transform_air(pollution_data, city_id)
                result_summary["counts"]["transform_air_records"] += air_count

                logger.info(f"FETCH_HISTORICAL_AIR_DATA ({city_name} @ {target_date})")
                historical_data = fetch_historical(city_id, formatted_gold, city_name)

                logger.info(f"CALCULATE_ROLLING_AVERAGES ({city_name} @ {target_date})")
                rolling_count, rolling_7d_added = calculate_rolling_averages(historical_data, ['aqi', 'pm2_5'], formatted_gold, city_name)
                result_summary["counts"]["transform_rolling_records"] += rolling_count

                current_stage = f"LOAD_GOLD_AIR_POLLUTION ({city_name} @ {target_date})"
                logger.info(f"[STAGE START: {current_stage}] Saving {rolling_count} gold records")
                loaded_count = load_gold_air_data_task(rolling_7d_added)
                result_summary["counts"]["load_gold_air_records"] += loaded_count

            result_summary["succeeded_cities"].append(city_name)
            logger.info(f"[CITY SUCCESS] Successfully processed all missing dates for {city_name}")
       
        except Exception as e:
            # 1. Record structured failure info
            failure_info = {
                "city": city_name,
                "failed_stage": current_stage,
                "error_type": type(e).__name__,
                "error_message": str(e),
            }
            result_summary["failed_cities"].append(failure_info)

            # 2. Log stage + full traceback clearly so a teammate knows exactly what broke
            logger.exception(
                f"[CITY FAILED] City '{city_name}' failed during stage '{current_stage}' "
                f"with {type(e).__name__}: {e}. Continuing to remaining cities..."
            )
            continue

    # 3. Check if any city failed after the loop finishes    
    if result_summary["failed_cities"]:
        result_summary["status"] = "FAILED"
        result_summary["failed_stage"] = result_summary["failed_cities"][0]["failed_stage"]
        result_summary["error"] = f"{len(result_summary['failed_cities'])} city(s) failed"
        logger.error(
            f"[PHASE 1 FAILED] Completed with {len(result_summary['failed_cities'])} failed city(s). "
            f"Failures: {result_summary['failed_cities']} | Partial counts: {result_summary['counts']}"
        )
        raise RuntimeError(
            f"ETL failed for {len(result_summary['failed_cities'])} city(s): {result_summary['failed_cities']}"
        )

    result_summary["status"] = "SUCCESS"
    logger.info(f"[PHASE 1 SUCCESS] ETL execution completed! Summary: {result_summary}")
    return result_summary
        

#--- PHASE 2: LLM Enrichment Flow --
# @flow(
#     name="City Air Tracker LLM Enrichment", 
#     log_prints=True, 
#     on_completion=[log_flow_success], 
#     on_failure=[log_flow_failure]
# )
# def llm_enrichment_flow():
#     """Phase 2: Scans for un-enriched rows, batches them, and calls LLM."""
#     logger = get_run_logger()
#     logger.info("Starting Phase 2 LLM Enrichment Worker Flow")
    
#     try:
#         llm_enrichment_task()
#         logger.info("Phase 2 LLM Enrichment completed successfully!")
#     except Exception as e:
#         logger.error(f"LLM Enrichment flow failed: {e}")
#         raise e

   
if __name__ == "__main__":
    main_etl_flow()