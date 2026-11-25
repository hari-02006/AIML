import time, urllib.request, sys
time.sleep(2)
pages = ['', 'Sales%20Analytics', 'Product%20Analytics']
for page in pages:
    url = f'http://localhost:8503{"/" if page=="" else "?page="+page}'
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            txt = resp.read().decode('utf-8')
            print(page or 'Dashboard', 'status', resp.status, 'error' if ('ImportError' in txt or 'NameError' in txt) else 'ok')
    except Exception as e:
        print('failed', page, e)
