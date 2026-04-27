from flask import Flask, request, jsonify
import re
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

app = Flask(__name__)

# Global driver instance (or pool) for server-side Selenium
# This needs careful management in a production environment (e.g., using a driver pool)
# For simplicity, we'll initialize one per request or manage a single one.
# For Railway, it's better to initialize a new driver for each request or use a pool
# if multiple concurrent requests are expected, but that adds complexity.
# Let's use a simple approach for now.

def arabic_to_english_num(text):
    arabic_nums = '٠١٢٣٤٥٦٧٨٩'
    english_nums = '0123456789'
    translation_table = str.maketrans(arabic_nums, english_nums)
    return text.translate(translation_table)

def parse_count_string(count_str):
    if not count_str: return 0
    count_str = count_str.replace(',', '').upper().strip()
    try:
        if 'K' in count_str:
            return int(float(count_str.replace('K', '')) * 1000)
        elif 'M' in count_str:
            return int(float(count_str.replace('M', '')) * 1000000)
        return int(float(count_str))
    except:
        return 0

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless") # Run in headless mode on server
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--mute-audio")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    
    # Important for Railway/Docker environments
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-setuid-sandbox")
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(30)
    return driver

def check_fb_logic_selenium(cookie_str):
    driver = None
    try:
        driver = setup_driver()
        driver.delete_all_cookies()
        driver.get("https://www.facebook.com/robots.txt") # Set domain for cookies
        
        for cookie_part in cookie_str.split(';'):
            if '=' in cookie_part:
                name, value = cookie_part.split('=', 1)
                try:
                    driver.add_cookie({
                        'name': name.strip(),
                        'value': value.strip(),
                        'domain': '.facebook.com'
                    })
                except:
                    pass
        
        uid_match = re.search(r'c_user=(\d+)', cookie_str)
        if not uid_match:
            return {"status": "Failed", "reason": "No UID in Cookie"}
        uid = uid_match.group(1)

        profile_url = f"https://www.facebook.com/profile.php?id={uid}"
        driver.get(profile_url)
        
        time.sleep(3) # Give time for page to load and modals to appear
        
        html_lower = driver.page_source.lower()
        current_url = driver.current_url.lower()
        
        # More thorough login detection
        logout_indicators = ["logout", "log out", "تسجيل الخروج", "خروج", "mbasic_logout_button", "sign out"]
        is_logged_in = any(kw in html_lower for kw in logout_indicators)
        
        if not is_logged_in:
            nav = driver.find_elements(By.XPATH, "//div[@role='navigation']")
            search = driver.find_elements(By.XPATH, "//input[@placeholder='Search Facebook' or @placeholder='بحث في فيسبوك']")
            profile_link = driver.find_elements(By.XPATH, "//a[contains(@href, '/profile.php') or contains(@href, 'facebook.com/me')]")
            is_logged_in = len(nav) > 0 or len(search) > 0 or len(profile_link) > 0

        login_indicators = [
            "//div[contains(text(), 'See more on Facebook')]",
            "//div[contains(text(), 'عرض المزيد على فيسبوك')]",
            "//form[@id='login_form']",
            "//input[@name='email' and @id='email']",
            "//button[@name='login']"
        ]
        for indicator in login_indicators:
            if driver.find_elements(By.XPATH, indicator):
                is_logged_in = False
                break

        if not is_logged_in:
            return {"status": "Failed", "reason": "Login Required/Checkpoint"}

        # Extract Data
        name = "Unknown"
        try:
            name_selectors = [
                "//h1", 
                "//span[contains(@class, 'x1heor9g')]", 
                "//div[@role='main']//h1",
                "//title"
            ]
            for selector in name_selectors:
                if selector == "//title":
                    t = driver.title
                else:
                    els = driver.find_elements(By.XPATH, selector)
                    t = els[0].text if els else ""
                
                if t and "facebook" not in t.lower() and len(t) > 2:
                    name = t.split('|')[0].strip()
                    break
        except:
            pass

        friends = "0"
        try:
            friends_xpaths = [
                "//span[contains(text(), 'friends') or contains(text(), 'الأصدقاء')]",
                "//a[contains(@href, 'friends')]//span",
                "//div[contains(text(), 'friends') or contains(text(), 'الأصدقاء')]",
                "//span[@class='x193iqbg']"
            ]
            
            for xpath in friends_xpaths:
                els = driver.find_elements(By.XPATH, xpath)
                for el in els:
                    txt = arabic_to_english_num(el.text)
                    match = re.search(r'([\d.,]+[KMB]?)', txt)
                    if match and int(parse_count_string(match.group(1))) > 0:
                        friends = str(parse_count_string(match.group(1)))
                        break
                if friends != "0":
                    break
            
            if friends == "0":
                page_text = driver.find_element(By.TAG_NAME, "body").text
                patterns = [
                    r'([\d.,]+)\s*(?:friends|أصدقاء|Friends)',
                    r'(?:friends|أصدقاء|Friends)\s*([\d.,]+)',
                    r'([\d.,]+)\s*(?:friend|صديق)'
                ]
                for pattern in patterns:
                    match = re.search(pattern, page_text.lower())
                    if match:
                        friends = str(parse_count_string(match.group(1)))
                        break
        except:
            pass

        has_pfp = "No"
        try:
            pfp_selectors = [
                "//image[@preserveAspectRatio='xMidYMid slice']",
                "//img[contains(@alt, 'profile') or contains(@alt, 'صورة')]",
                "//div[@aria-label='Profile picture' or @aria-label='صورة الملف الشخصي']//img"
            ]
            
            for selector in pfp_selectors:
                els = driver.find_elements(By.XPATH, selector)
                if els:
                    src = els[0].get_attribute("src") or els[0].get_attribute("xlink:href")
                    if src and "fbcdn.net" in src:
                        if not any(kw in src for kw in ["silhouette", "static_type_profile", "14713327_229971934073277"]):
                            has_pfp = "Yes"
                            break
        except:
            pass

        return {
            "status": "Live",
            "name": name,
            "friends": friends,
            "pfp": has_pfp
        }
    except Exception as e:
        return {"status": "Error", "reason": str(e)}
    finally:
        if driver:
            driver.quit()

@app.route('/check', methods=['POST'])
def check_account():
    data = request.json
    cookie = data.get('cookie')
    if not cookie:
        return jsonify({"error": "No cookie provided"}), 400
    
    result = check_fb_logic_selenium(cookie)
    return jsonify(result)

@app.route('/')
def home():
    return "FB Checker API with Selenium is Running!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
