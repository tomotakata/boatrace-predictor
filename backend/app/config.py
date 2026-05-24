import os
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
BOATFRONTIER_EMAIL = os.environ.get("BOATFRONTIER_EMAIL", "")
BOATFRONTIER_PASSWORD = os.environ.get("BOATFRONTIER_PASSWORD", "")

def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)
