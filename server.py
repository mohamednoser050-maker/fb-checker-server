from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

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

def check_fb_logic(cookie_str):
    headers = {
        'authority': 'mbasic.facebook.com',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-US,en;q=0.9,ar-EG;q=0.8,ar;q=0.7',
        'cookie': cookie_str,
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
    }
    try:
        uid_match = re.search(r'c_user=(\d+)', cookie_str)
        if not uid_match: return {"status": "Failed", "reason": "No UID"}
        uid = uid_match.group(1)
        
        # Use mbasic for speed and server compatibility
        response = requests.get(f'https://mbasic.facebook.com/profile.php?id={uid}', headers=headers, timeout=15)
        html_lower = response.text.lower()
        
        is_live = any(kw in html_lower for kw in ["logout", "log out", "تسجيل الخروج", "خروج", "mbasic_logout_button"])
        if not is_live:
            return {"status": "Failed", "reason": "Login Required"}
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Name
        name = "Unknown"
        title_tag = soup.find('title')
        if title_tag: name = title_tag.text.split('|')[0].strip()
        
        # Friends
        friends = "0"
        for link in soup.find_all('a', href=True):
            if '/friends' in link.get('href', '').lower():
                txt = arabic_to_english_num(link.text)
                match = re.search(r'([\d.,]+)', txt)
                if match: 
                    friends = str(parse_count_string(match.group(1)))
                    break
        
        # PFP
        has_pfp = "No"
        pfp_img = soup.find('img', alt=lambda x: x and any(kw in x.lower() for kw in ['profile', 'صورة']))
        if pfp_img and "fbcdn.net" in pfp_img.get('src', '') and "silhouette" not in pfp_img.get('src', ''):
            has_pfp = "Yes"
            
        return {"status": "Live", "name": name, "friends": friends, "pfp": has_pfp}
    except Exception as e:
        return {"status": "Error", "reason": str(e)}

@app.route('/check', methods=['POST'])
def check_account():
    data = request.json
    cookie = data.get('cookie')
    if not cookie:
        return jsonify({"error": "No cookie provided"}), 400
    
    result = check_fb_logic(cookie)
    return jsonify(result)

@app.route('/')
def home():
    return "FB Checker API is Running!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
