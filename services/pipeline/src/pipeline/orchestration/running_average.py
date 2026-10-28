import logging
from supabase import Client

LOG = logging.getLogger(__name__)


def update_running_average(supabase_client: Client):
    """
    Updates the 10-day PM2.5 rolling average for each city
    in the gold_air_data table.
    """

    if not isinstance(supabase_client, Client):
        raise ValueError("A valid Supabase client is required.")

    try:
        response = supabase_client.rpc(
            "update_pm25_running_average"
        ).execute()

        LOG.info("Successfully updated PM2.5 running averages.")
        return response

    except Exception as e:
        LOG.error("Failed to update running averages: %s", e)
        raise RuntimeError(f"Failed to update running averages: {e}") from e
