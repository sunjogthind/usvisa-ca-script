import random
import re
import shutil
import subprocess
import traceback
from datetime import datetime, timedelta
from time import sleep
from typing import Union, List

import requests
from selenium import webdriver
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from legacy.gmail import GMail, Message
from legacy_rescheduler import legacy_reschedule, UnverifiedReschedule
from request_tracker import RequestTracker
from settings import *


class SoftBanDetected(Exception):
    pass


soft_ban_streak = 0
login_fail_streak = 0


def log_message(message: str) -> None:
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")


def jittered_delay(base_delay: float) -> float:
    return base_delay + random.uniform(0, DATE_REQUEST_JITTER)


def seconds_until_poll_window() -> float:
    """Return seconds to sleep until we're inside the allowed polling window.
    Returns 0 if polling is allowed now (or the window is disabled)."""
    if POLL_START_HOUR == POLL_END_HOUR:
        return 0
    now = datetime.now()
    if POLL_START_HOUR <= now.hour < POLL_END_HOUR:
        return 0
    target = now.replace(hour=POLL_START_HOUR, minute=0, second=0, microsecond=0)
    if now.hour >= POLL_END_HOUR:
        target = target + timedelta(days=1)
    return max(0, (target - now).total_seconds())

def send_email_notification(subject: str, body: str) -> None:
    if not (GMAIL_EMAIL and GMAIL_APPLICATION_PWD and RECEIVER_EMAIL):
        log_message("Email notification skipped: Gmail settings not configured")
        return
    try:
        gmail = GMail(f"{GMAIL_SENDER_NAME} <{GMAIL_EMAIL}>", GMAIL_APPLICATION_PWD)
        msg = Message(
            subject,
            to=f"{RECEIVER_NAME} <{RECEIVER_EMAIL}>",
            text=body
        )
        gmail.send(msg)
        gmail.close()
        log_message(f"Email notification sent: {subject}")
    except Exception as e:
        log_message(f"Email notification failed (non-blocking): {e}")


def send_ntfy_notification(subject: str, body: str, priority: str = "high", tags: str = "calendar") -> None:
    if not NTFY_TOPIC:
        return
    try:
        requests.post(
            f"{NTFY_SERVER.rstrip('/')}/{NTFY_TOPIC}",
            data=body.encode("utf-8"),
            headers={"Title": subject, "Priority": priority, "Tags": tags},
            timeout=10,
        )
        log_message(f"ntfy notification sent: {subject}")
    except Exception as e:
        log_message(f"ntfy notification failed (non-blocking): {e}")


def send_macos_notification(subject: str, body: str, sound: bool = True) -> None:
    if not MACOS_NOTIFY:
        return
    try:
        safe_body = body.replace('"', "'")
        safe_subject = subject.replace('"', "'")
        script = f'display notification "{safe_body}" with title "{safe_subject}"'
        if sound:
            script += ' sound name "Glass"'
        subprocess.run(["osascript", "-e", script], timeout=10, check=False)
    except Exception as e:
        log_message(f"macOS notification failed (non-blocking): {e}")


def send_notification(subject: str, body: str, critical: bool = True) -> None:
    """Fire all configured notification channels. Each is non-blocking.
    critical=True uses high priority + sound (booking/failures); False is a quiet
    status update (start/pause/resume)."""
    send_email_notification(subject, body)
    send_ntfy_notification(subject, body, priority="high" if critical else "default")
    send_macos_notification(subject, body, sound=critical)


def get_chrome_driver() -> (WebDriver, str):
    options = webdriver.ChromeOptions()
    user_agent = random.choice(USER_AGENTS)
    if not SHOW_GUI:
        options.add_argument("headless")
        options.add_argument("window-size=1920x1080")
        options.add_argument("disable-gpu")
    options.add_argument(f'user-agent={user_agent}')
    options.add_experimental_option("detach", DETACH)
    options.add_argument('--incognito')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    user_data_dir = f'/tmp/chrome-{datetime.now().strftime("%Y%m%d-%H%M%S")}-{random.randint(1000, 9999)}'
    options.add_argument(f'--user-data-dir={user_data_dir}')
    driver = webdriver.Chrome(options=options)
    log_message(f"New session using UA: ...{user_agent[-40:]}")
    return driver, user_data_dir


def login(driver: WebDriver) -> None:
    driver.get(LOGIN_URL)
    timeout = TIMEOUT

    email_input = WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((By.ID, "user_email"))
    )
    email_input.send_keys(USER_EMAIL)

    password_input = WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((By.ID, "user_password"))
    )
    password_input.send_keys(USER_PASSWORD)

    policy_checkbox = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.CLASS_NAME, "icheckbox"))
    )
    policy_checkbox.click()

    login_button = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.NAME, "commit"))
    )
    login_button.click()


def get_appointment_page(driver: WebDriver) -> None:
    timeout = TIMEOUT
    continue_button = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.LINK_TEXT, "Continue"))
    )
    continue_button.click()
    sleep(2)
    current_url = driver.current_url
    url_id = re.search(r"/(\d+)", current_url).group(1)
    appointment_url = APPOINTMENT_PAGE_URL.format(id=url_id)
    driver.get(appointment_url)


def get_available_dates(
    driver: WebDriver, request_tracker: RequestTracker, consulate_id: int
) -> Union[List[datetime.date], None]:
    request_tracker.log_retry()
    request_tracker.retry()
    schedule_base = driver.current_url.split("/appointment")[0]
    suffix = AVAILABLE_DATE_REQUEST_SUFFIX_TEMPLATE.format(consulate_id=consulate_id)
    request_url = schedule_base + "/appointment" + suffix
    request_header_cookie = "".join(
        [f"{cookie['name']}={cookie['value']};" for cookie in driver.get_cookies()]
    )
    request_headers = REQUEST_HEADERS.copy()
    request_headers["Cookie"] = request_header_cookie
    request_headers["User-Agent"] = driver.execute_script("return navigator.userAgent")
    request_headers["Referer"] = driver.current_url
    try:
        response = requests.get(request_url, headers=request_headers)
    except Exception as e:
        log_message(f"Get available dates request failed: {e}")
        return None
    if response.status_code != 200:
        log_message(f"Failed with status code {response.status_code}")
        log_message(f"Response Text: {response.text[:300]}")
        return None
    try:
        dates_json = response.json()
    except:
        if "sign_in" in response.text or response.text.lstrip().startswith("<"):
            log_message("Received HTML instead of JSON - session likely expired or request was blocked, starting a new session")
        else:
            log_message("Failed to decode json")
        log_message(f"Response Text: {response.text[:300]}")
        return None
    dates = [datetime.strptime(item["date"], "%Y-%m-%d").date() for item in dates_json]
    return dates


def find_target_date(dates: List[datetime.date]) -> Union[datetime.date, None]:
    earliest_acceptable_date = datetime.strptime(EARLIEST_ACCEPTABLE_DATE, "%Y-%m-%d").date()
    latest_acceptable_date = datetime.strptime(LATEST_ACCEPTABLE_DATE, "%Y-%m-%d").date()
    for candidate in sorted(dates):
        if not (earliest_acceptable_date <= candidate <= latest_acceptable_date):
            continue
        excluded = False
        for start, end in EXCLUSION_DATE_RANGES:
            if datetime.strptime(start, "%Y-%m-%d").date() <= candidate <= datetime.strptime(end, "%Y-%m-%d").date():
                log_message(f"Skipping {candidate}: falls in excluded date range {start} to {end}")
                excluded = True
                break
        if not excluded:
            return candidate
    return None


def try_book(driver: WebDriver, target_date: datetime.date, consulate_id: int, consulate_name: str) -> Union[bool, None]:
    """Attempt to book target_date at the given consulate.
    Returns True on success/stop, None if booking failed but polling should continue."""
    log_message(f"FOUND SLOT ON {target_date} at {consulate_name}!!!")
    try:
        if legacy_reschedule(driver, target_date, consulate_id):
            log_message("SUCCESSFULLY RESCHEDULED!!!")
            send_notification(
                f"Visa Appointment Rescheduled for {target_date}",
                f"Your visa appointment has been successfully rescheduled to {target_date} at {consulate_name} consulate."
            )
            return True
        return None
    except UnverifiedReschedule as e:
        log_message(f"STOPPING: {e}")
        send_notification(
            "Visa Rescheduler: MANUAL VERIFICATION NEEDED",
            f"The rescheduler clicked confirm for {target_date} at {consulate_name} but could not verify success. "
            "Please log in to ais.usvisa-info.com and check your appointment. The program has stopped to avoid wasting reschedule attempts."
        )
        return True
    except Exception as e:
        log_message(f"Rescheduling failed: {e}")
        traceback.print_exc()
        return None


def reschedule(driver: WebDriver, retryCount: int = 0) -> bool:
    global soft_ban_streak
    date_request_tracker = RequestTracker(
        retryCount if (retryCount > 0) else DATE_REQUEST_MAX_RETRY,
        DATE_REQUEST_DELAY * retryCount if (retryCount > 0) else DATE_REQUEST_MAX_TIME
    )
    while date_request_tracker.should_retry():
        if seconds_until_poll_window() > 0:
            log_message("Polling window closed - ending session until it reopens")
            return False

        cycle_results = {}  # consulate name -> list[date] | None (None = request error)
        for idx, name in enumerate(USER_CONSULATES):
            if idx > 0:
                sleep(random.uniform(2, 5))  # small human-like gap between consulates
            consulate_id = CONSULATES[name]
            dates = get_available_dates(driver, date_request_tracker, consulate_id)
            cycle_results[name] = dates
            if dates:
                target_date = find_target_date(dates)
                if target_date is not None:
                    result = try_book(driver, target_date, consulate_id, name)
                    if result is True:
                        return True
                    # booking failed (slot gone / error) - keep polling other consulates

        responded = [v for v in cycle_results.values() if v is not None]
        if not responded:
            log_message("Error occured when requesting available dates (all consulates)")
            sleep(jittered_delay(DATE_REQUEST_DELAY))
            continue
        if all(len(v) == 0 for v in responded):
            # every consulate that responded returned an empty list -> server busy / soft-ban
            raise SoftBanDetected
        if soft_ban_streak > 0:
            log_message("Date list is flowing again - resetting soft-ban backoff")
            soft_ban_streak = 0

        summary = ", ".join(
            (f"{name}: {len(v)} (earliest {min(v)})" if v else f"{name}: 0")
            for name, v in cycle_results.items() if v is not None
        )
        delay = jittered_delay(DATE_REQUEST_DELAY)
        next_check = (datetime.now() + timedelta(seconds=delay)).strftime("%H:%M")
        log_message(
            f"No acceptable date in {EARLIEST_ACCEPTABLE_DATE}..{LATEST_ACCEPTABLE_DATE}. "
            f"[{summary}]. Next check ~{next_check}"
        )
        sleep(delay)
    return False


def reschedule_with_new_session(retryCount: int = DATE_REQUEST_MAX_RETRY) -> bool:
    global soft_ban_streak, login_fail_streak
    driver, user_data_dir = get_chrome_driver()
    try:
        session_failures = 0
        timeout = TIMEOUT
        while session_failures < NEW_SESSION_AFTER_FAILURES:
            try:
                login(driver)
                get_appointment_page(driver)
                policy_checkbox_limit = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.CLASS_NAME, "icheckbox")))
                policy_checkbox_limit.click()
                continue_button = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.NAME, "commit")))
                continue_button.click() 
                break
            except Exception as e:
                log_message(f"Unable to get appointment page: {e}")
                session_failures += 1
                sleep(FAIL_RETRY_DELAY)
                continue
        else:
            # Loop exhausted without a successful session setup (login/nav broken).
            login_fail_streak += 1
            log_message(f"Could not set up a session after {NEW_SESSION_AFTER_FAILURES} attempts (streak: {login_fail_streak})")
            if login_fail_streak == 1:
                send_notification(
                    "Visa Bot: login/session failing",
                    "The bot could not log in or reach the appointment page. This may mean the site is "
                    "blocking automated access, your login is being challenged, or the site layout changed. "
                    "It will keep retrying. Check ais.usvisa-info.com manually if this persists."
                )
            return False
        login_fail_streak = 0
        return reschedule(driver, retryCount)
    except SoftBanDetected:
        soft_ban_streak += 1
        cooldown = min(SOFT_BAN_COOLDOWN * (2 ** (soft_ban_streak - 1)), SOFT_BAN_COOLDOWN_MAX)
        log_message(f"Empty date list received - likely soft-banned by the server (streak: {soft_ban_streak}). Cooling down for {cooldown // 60} minutes before retrying")
        send_notification(
            "Visa Bot: soft-banned, cooling down",
            f"The server returned an empty date list (soft-ban streak {soft_ban_streak}). "
            f"Pausing for {cooldown // 60} minutes, then a fresh session will retry automatically."
        )
        sleep(cooldown)
        return False
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        shutil.rmtree(user_data_dir, ignore_errors=True)


if __name__ == "__main__":
    session_count = 0
    log_message(f"Attempting to reschedule for email: {USER_EMAIL}")
    log_message(f"User Consulate: {USER_CONSULATE}")
    log_message(f"Earliest Acceptable Date: {EARLIEST_ACCEPTABLE_DATE}")
    log_message(f"Latest Acceptable Date: {LATEST_ACCEPTABLE_DATE}")

    if EXCLUSION_DATE_RANGES:
        log_message("Excluded Date Ranges:")
        for i, (start, end) in enumerate(EXCLUSION_DATE_RANGES, 1):
            log_message(f"  Range {i}: {start} to {end}")
    else:
        log_message("No date ranges excluded")

    if POLL_START_HOUR != POLL_END_HOUR:
        log_message(f"Polling window: {POLL_START_HOUR:02d}:00-{POLL_END_HOUR:02d}:00 local time")

    send_notification(
        "Visa Bot: started",
        f"Now watching {USER_CONSULATE} for slots between {EARLIEST_ACCEPTABLE_DATE} and {LATEST_ACCEPTABLE_DATE}."
        + (f" Polling window {POLL_START_HOUR:02d}:00-{POLL_END_HOUR:02d}:00." if POLL_START_HOUR != POLL_END_HOUR else ""),
        critical=False,
    )

    while True:
        wait = seconds_until_poll_window()
        if wait > 0:
            log_message(f"Outside polling window - sleeping {int(wait // 60)} min until {POLL_START_HOUR:02d}:00")
            send_notification(
                "Visa Bot: paused for the night",
                f"Outside polling window ({POLL_START_HOUR:02d}:00-{POLL_END_HOUR:02d}:00). "
                f"Sleeping ~{int(wait // 60)} min and resuming at {POLL_START_HOUR:02d}:00.",
                critical=False,
            )
            sleep(wait)
            send_notification(
                "Visa Bot: resumed",
                f"Polling window reopened at {POLL_START_HOUR:02d}:00 - back to checking for slots.",
                critical=False,
            )
        session_count += 1
        log_message(f"Attempting with new session #{session_count}")
        rescheduled = reschedule_with_new_session()
        if rescheduled:
            break
        sleep(NEW_SESSION_DELAY)
    send_notification(
        "Rescheduler Program Exited",
        f"The rescheduler program has exited on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}."
    )
