import os
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
# Support both naming conventions
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
BOATFRONTIER_EMAIL = os.environ.get("BOATFRONTIER_EMAIL", "").strip()
BOATFRONTIER_PASSWORD = os.environ.get("BOATFRONTIER_PASSWORD", "").strip()

def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)
