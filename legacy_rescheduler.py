from time import sleep
from datetime import datetime, date

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.webdriver import WebDriver

from settings import TEST_MODE, NUM_PARTICIPANTS


class UnverifiedReschedule(Exception):
    pass

# This is frankly very, very bad and should be rewritten with requests
# when I get a test account
def legacy_reschedule(driver: WebDriver, date_to_book: date):
    driver.refresh()

    # Continue btn: applicable when there are more than one applicant for scheduling
    if NUM_PARTICIPANTS > 1:
        continueBtn = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//main[@id='main']/div[@class='mainContent']/form/div[2]/div/input"))
            )
        continueBtn.click()

    date_selection_box = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (
                By.ID, 'appointments_consulate_appointment_date_input'
            )
        )
    )
    sleep(2)
    date_selection_box.click()

    # Move to next month
    def next_month():
        driver.find_element(By.XPATH, "//div[@id='ui-datepicker-div']/div[2]/div/a").click()

    # Find the clickable cell for the exact target date in the currently displayed month
    def find_target_date_btn():
        month = driver.find_element(By.XPATH, "//div[@id='ui-datepicker-div']/div[1]/table/tbody")
        cells = month.find_elements(By.TAG_NAME, "td")
        for cell in cells:
            if cell.get_attribute("class") != " undefined":
                continue
            if (cell.get_attribute("data-year") == str(date_to_book.year)
                    and cell.get_attribute("data-month") == str(date_to_book.month - 1)):
                btn = cell.find_element(By.TAG_NAME, "a")
                if btn.text.strip() == str(date_to_book.day):
                    return btn
        return None

    print(f"Looking for {date_to_book} in calendar...")
    ava_date_btn = find_target_date_btn()
    months_moved = 0
    while ava_date_btn is None and months_moved < 36:
        next_month()
        months_moved += 1
        ava_date_btn = find_target_date_btn()
    if ava_date_btn is None:
        print(f"{datetime.now().strftime('%H:%M:%S')} SLOT '{date_to_book}' not found in calendar - no longer available\n")
        return False

    print("Trying to pick time and reschedule...")
    ava_date_btn.click()

    # confirm selected date
    sleep(2)
    date_box = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (
                By.ID, 'appointments_consulate_appointment_date'
            )
        )
    )
    date_selected = datetime.strptime(date_box.get_attribute('value'), "%Y-%m-%d").date()
    print(date_selected)
    if date_selected != date_to_book:
        print(f"{datetime.now().strftime('%H:%M:%S')} Selected date '{date_selected}' does not match target '{date_to_book}' - aborting\n")
        return False
    else:
        print(f"{datetime.now().strftime('%H:%M:%S')} SLOT '{date_selected}' is still available. Booking....\n")

    # Select time of the date:
    sleep(2)
    appointment_time = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.ID, "appointments_consulate_appointment_time"))
    )
    appointment_time.click()
    appointment_time_options = appointment_time.find_elements(By.TAG_NAME, "option")
    appointment_time_options[len(appointment_time_options) - 1].click()

    # Click "Reschedule"
    driver.find_element(
        By.XPATH,
        "//form[@id='appointment-form']/div[2]/fieldset/ol/li/input",
    ).click()
    sleep(2)
    try:
        confirm = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "/html/body/div[6]/div/div/a[2]"))
        )
    except Exception as e:
        print(f"{datetime.now().strftime('%H:%M:%S')} Confirmation dialog not found: {e}\n")
        return False
    sleep(2)
    driver.implicitly_wait(0.1)
    if TEST_MODE:
        print(f"{datetime.now().strftime('%H:%M:%S')} TEST_MODE enabled - skipping final confirmation click\n")
        return False
    confirm.click()
    sleep(5)
    page_source = driver.page_source.lower()
    success_indicators = [
        "successfully scheduled",
        "successfully rescheduled",
        "you have successfully",
    ]
    if any(indicator in page_source for indicator in success_indicators):
        print(f"{datetime.now().strftime('%H:%M:%S')} Reschedule confirmed by page message\n")
        return True
    try:
        WebDriverWait(driver, 10).until(
            EC.invisibility_of_element_located((By.ID, "appointments_consulate_appointment_date_input"))
        )
        print(f"{datetime.now().strftime('%H:%M:%S')} Reschedule likely succeeded (appointment form closed). PLEASE VERIFY YOUR APPOINTMENT MANUALLY at ais.usvisa-info.com\n")
        return True
    except Exception:
        raise UnverifiedReschedule(
            "Confirm was clicked but reschedule success could not be verified. "
            "Stopping to avoid wasting limited reschedule attempts. "
            "PLEASE CHECK YOUR APPOINTMENT MANUALLY at ais.usvisa-info.com"
        )
