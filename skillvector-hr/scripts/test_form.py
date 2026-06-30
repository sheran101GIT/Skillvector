import sys
import os
import json
from dotenv import load_dotenv

# Add parent dir to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load active .env
load_dotenv()

sa_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
print(f"GOOGLE_SERVICE_ACCOUNT_JSON length: {len(sa_json) if sa_json else 0}")

if sa_json:
    try:
        json.loads(sa_json)
        print("JSON parsed successfully.")
    except Exception as e:
        print(f"JSON parsing failed: {e}")

# Try to connect
from app.google_forms_service import get_google_forms_service, extract_form_id_from_url
url = "https://docs.google.com/forms/d/e/1FAIpQLSeEVgWvw5jO4H17EOtsj6DbHK3hiWQu8YkTk19m0JkCZvuNVQ/viewform"
form_id = extract_form_id_from_url(url)
print(f"Extracted Form ID: {form_id}")

try:
    svc = get_google_forms_service()
    meta = svc.get_form_metadata(form_id)
    print("Successfully fetched form metadata:")
    print(f"   Title: {meta['title']}")
    print(f"   Questions count: {len(meta['questions'])}")
except Exception as e:
    print(f"Failed: {e}")
