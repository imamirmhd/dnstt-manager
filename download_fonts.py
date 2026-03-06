import urllib.request
import re
import os
import time

font_urls = [
    "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap",
    "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap"
]
chartjs_url = "https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"

os.makedirs("static/fonts", exist_ok=True)
os.makedirs("static/css", exist_ok=True)
os.makedirs("static/js", exist_ok=True)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def fetch_with_retry(url, max_retries=10, timeout=15):
    for i in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except Exception as e:
            print(f"Fetch failed for {url}: {e}. Retrying {i+1}/{max_retries}...")
            time.sleep(3)
    raise Exception(f"Failed to fetch {url} after {max_retries} retries")

all_css = []

for font_url in font_urls:
    print(f"Fetching CSS: {font_url}")
    css_content = fetch_with_retry(font_url).decode('utf-8')
    
    urls = re.findall(r'url\((https://[^)]+)\)', css_content)
    for url in urls:
        font_filename = url.split('/')[-1]
        local_font_path = f"../fonts/{font_filename}"
        
        # Download the font
        font_path = f"static/fonts/{font_filename}"
        if not os.path.exists(font_path) or os.path.getsize(font_path) == 0:
            print(f"Downloading {font_filename}...")
            font_data = fetch_with_retry(url)
            with open(font_path, "wb") as f:
                f.write(font_data)
        else:
            print(f"Already downloaded {font_filename}")
        
        css_content = css_content.replace(url, local_font_path)
        
    all_css.append(css_content)

with open("static/css/fonts.css", "w") as f:
    f.write("\n".join(all_css))

print("Fonts downloaded and CSS generated successfully.")

print("Downloading Chart.js...")
try:
    chart_path = "static/js/chart.umd.min.js"
    if not os.path.exists(chart_path) or os.path.getsize(chart_path) == 0:
        chart_data = fetch_with_retry(chartjs_url)
        with open(chart_path, "wb") as f:
            f.write(chart_data)
        print("Chart.js downloaded successfully.")
    else:
        print("Chart.js already exists.")
except Exception as e:
    print(f"Failed to download Chart.js: {e}")
