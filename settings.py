from dotenv import load_dotenv
import os
from datetime import datetime
# Load environment variables
load_dotenv()

# Account Info
USER_EMAIL = os.getenv("USER_EMAIL")
USER_PASSWORD = os.getenv("USER_PASSWORD")
NUM_PARTICIPANTS = 1

# Say you want an appointment no later than Mar 14, 2024
# Please strictly follow the YYYY-MM-DD format for all dates

EARLIEST_ACCEPTABLE_DATE = os.getenv("EARLIEST_ACCEPTABLE_DATE")
LATEST_ACCEPTABLE_DATE = os.getenv("LATEST_ACCEPTABLE_DATE")

# Date exclusion ranges
EXCLUSION_DATE_RANGES = []
if EARLIEST_ACCEPTABLE_DATE and LATEST_ACCEPTABLE_DATE:
    try:
        earliest_acceptable_date = datetime.strptime(EARLIEST_ACCEPTABLE_DATE, "%Y-%m-%d").date()
        latest_acceptable_date = datetime.strptime(LATEST_ACCEPTABLE_DATE, "%Y-%m-%d").date()
        
        for i in range(1, 10):  # Support up to 9 exclusion ranges
            start = os.getenv(f"EXCLUSION_START_DATE_{i}")
            end = os.getenv(f"EXCLUSION_END_DATE_{i}")
            if start and end:
                try:
                    exclusion_start_date = datetime.strptime(start, "%Y-%m-%d").date()
                    exclusion_end_date = datetime.strptime(end, "%Y-%m-%d").date()
                    if (exclusion_start_date < exclusion_end_date and 
                        exclusion_start_date > earliest_acceptable_date and 
                        exclusion_end_date < latest_acceptable_date):
                        EXCLUSION_DATE_RANGES.append((start, end))
                except ValueError:
                    print(f"Invalid date format in exclusion range {start} to {end}")
    except ValueError:
        print("Invalid date format in EARLIEST_ACCEPTABLE_DATE or LATEST_ACCEPTABLE_DATE")

# Your consulate's city
CONSULATES = {
    "Calgary": 89,
    "Halifax": 90,
    "Montreal": 91,
    "Ottawa": 92,
    "Quebec": 93,
    "Toronto": 94,
    "Vancouver": 95
} # Only Toronto and Vancouver consulates are verified
# Choose a city from the list above
USER_CONSULATE = os.getenv("USER_CONSULATE")

_missing = [name for name, value in [
    ("USER_EMAIL", USER_EMAIL),
    ("USER_PASSWORD", USER_PASSWORD),
    ("EARLIEST_ACCEPTABLE_DATE", EARLIEST_ACCEPTABLE_DATE),
    ("LATEST_ACCEPTABLE_DATE", LATEST_ACCEPTABLE_DATE),
    ("USER_CONSULATE", USER_CONSULATE),
] if not value]
if _missing:
    raise SystemExit(f"Missing required .env variables: {', '.join(_missing)}")
if USER_CONSULATE not in CONSULATES:
    raise SystemExit(f"USER_CONSULATE must be one of: {', '.join(CONSULATES)}")

# The following is only required for the Gmail notification feature
# Gmail login info
GMAIL_SENDER_NAME = os.getenv("GMAIL_SENDER_NAME")
GMAIL_EMAIL = os.getenv("GMAIL_EMAIL")
GMAIL_APPLICATION_PWD = os.getenv("GMAIL_APPLICATION_PWD")

# Email notification receiver info
RECEIVER_NAME = os.getenv("RECEIVER_NAME")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")

# Free notification channels (no Gmail password needed)
# ntfy.sh push: set NTFY_TOPIC in .env to a unique/hard-to-guess topic name,
# install the ntfy app, and subscribe to that same topic. Leave blank to disable.
NTFY_SERVER = os.getenv("NTFY_SERVER") or "https://ntfy.sh"
NTFY_TOPIC = os.getenv("NTFY_TOPIC")
# Local macOS desktop notification + sound (only useful while at the laptop).
MACOS_NOTIFY = True

# Override with local, for developers
# from local import *

# See the automation in action
SHOW_GUI = False  # toggle to false if you don't want to see the browser

# If you just want to see the program run WITHOUT clicking the confirm reschedule button
# For testing, also set a date really far away so the app actually tries to reschedule
TEST_MODE = False

# Don't change the following unless you know what you are doing
DETACH = False
NEW_SESSION_AFTER_FAILURES = 5
NEW_SESSION_DELAY = 300
TIMEOUT = 10
FAIL_RETRY_DELAY = 180
DATE_REQUEST_DELAY = 300
DATE_REQUEST_JITTER = 240
DATE_REQUEST_MAX_RETRY = 20
DATE_REQUEST_MAX_TIME = 90 * 60
SOFT_BAN_COOLDOWN = 20 * 60
SOFT_BAN_COOLDOWN_MAX = 60 * 60

# Only poll during these local hours (24h). Slots are released during business
# hours; polling overnight just burns requests and looks bot-like.
# Set POLL_START_HOUR = POLL_END_HOUR to disable and poll 24/7.
POLL_START_HOUR = 6
POLL_END_HOUR = 20

# Rotated per session so repeated visits don't share one fingerprint.
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]
LOGIN_URL = "https://ais.usvisa-info.com/en-ca/niv/users/sign_in"
AVAILABLE_DATE_REQUEST_SUFFIX = f"/days/{CONSULATES[USER_CONSULATE]}.json?appointments[expedite]=false"
APPOINTMENT_PAGE_URL = "https://ais.usvisa-info.com/en-ca/niv/schedule/{id}/appointment"
PAYMENT_PAGE_URL = "https://ais.usvisa-info.com/en-ca/niv/schedule/{id}/payment"
REQUEST_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}
