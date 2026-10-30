import logging
from typing import Optional
from supabase import Client

logger = logging.getLogger(__name__)

def get_city_from_cache(city: str, supabase_client: Client) -> Optional[dict]:
    """
    Checks gold_cities for an existing record. 
    If found, returns the required parameters for fetching air pollution data, else None.
    """
    
    try:
        response = supabase_client.table("gold_cities") \
            .select("*") \
            .eq("city", city) \
            .execute()
        
        if response.data and len(response.data) > 0:
            record = response.data[0]
            return {
                'city': record.get('city'),
                'latitude': record.get('lat'),
                'longitude': record.get('lon')
            }
            
    except Exception as e:
        logger.warning("Cache check failed for '%s': %s", city, e)
        
    return None