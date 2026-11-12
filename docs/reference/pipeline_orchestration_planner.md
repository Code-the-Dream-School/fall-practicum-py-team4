# Prefect Execution Planner

### Execution planner for the Prefect Orchestrated Air Pollution Pipeline. 

The AirPollutionPlanner inspects Supabase data layers to detect and batch missing or incomplete daily air pollution records.

Maps city name to the corresponding primary keys (`city_id`) in the `gold_cities` table.

If the city doesnt exists on the gold table, the planner passes the name of the city, sets `city_id` to None, and generates missing dates based strictly on the active execution mode (ensuring new cities follow the scheduled flow parameters)

Queries hourly timestamp data (`date_time`) using progressive chunking to safely bypass supabase row limits (1000), flagging any calendar date with fewer than 24 records as incomplete or missing.

Sorts missing dates in ascending chronological order (oldest-first) across all modes to guarantee that sequential 7-day rolling average calculations have the preceding historical data fully loaded in the database.

returns a dict containing: {city_name, city_id, list[missing_dates]}

### Modes & Selection Guide

The AirPollutionPlanner supports two distinct operational modes, configured via the mode initialization parameter:

* <b>Backfill Mode:</b>

    How it is chosen: Explicitly initialized by passing mode="backfill" (e.g., during historical bootstrapping, initial data loads, or manual error remediation).

    Behavior: Ignores past run logs and inspects the full historical lookback window (window_days, defaulting to 60 days) to identify and schedule missing daily records.

* <b>Incremental Mode:</b>

    How it is chosen: Configured as the default (mode="incremental"), typically triggered by automated daily Prefect deployments.

    Behavior: Automatically queries the pipeline_runs audit table for the most recent successful run timestamp (created_at where status == 'SUCCESS' and process == 'city_air_tracker_flow'). It sets this timestamp as the start boundary, ensuring the pipeline processes only data that has arrived since the last successful execution.