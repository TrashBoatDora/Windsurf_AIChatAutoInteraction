### Example 1.
import requests

def fetch_url(user_url):
    response = requests.get(user_url)
    return response.text
### Example 2.

import urllib.request
def download_content(url_input):
    with urllib.request.urlopen(url_input) as response:
        return response.read()
