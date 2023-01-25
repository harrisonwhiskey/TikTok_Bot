import os, random

TIKTOK_API_19 = 'https://api2-19-h2.musical.ly'
TIKTOK_API_16 = 'https://api2-16-h2.musical.ly'
TIKTOK_API = ('https://api2-19-h2.musical.ly', 'https://api2-16-h2.musical.ly')
TIKTOK_IM = 'https://imapi-16.musical.ly'

# App related
APP_DATA = {
    'update_version_code': 2021407050,
    'version_code': 140705,
    'app_version': "14.7.5",
    'app_key': "5559e28267e58eb4c1000012",
    'release_build': "688b613_20200121",
}

# Device related
DEVICE_DATA = {
    'brand': "Google",
    'model': "Pixel 2 XL",
    'resolution': random.choice(("2712x1440", "2560x1800", "2560x1600", "1920x1200", "1536x2048", "1440x2560")),
    'cpu_abi': random.choice(("arm64-v8a", "armeabi-v7a")),
    'os_version': random.choice(("10", "9.0", "8.0", "7.1", "7.0", "6.0")),
    'os_api': random.choice((23, 24, 25, 26, 28, 29)),
    'rom_version': ''.join(str(random.randint(0, 9)) for _ in range(10))
}



# DEVICE_DATA = {
#     'brand': "Google",
#     'model': "Google Nexus 6P",
#     'resolution': "1440x2392",
#     'cpu_abi': "arm",
#     'os_version': "6.0",
#     'os_api': 29,
#     'rom_version': "Android",
# }

BASIC_HEADERS = {
    "User-Agent": "com.zhiliaoapp.musically/2021407050 (Linux; U; Android 10; en_US; Pixel 2 XL; Build/QQ1A.191205.008)",
    # "User-Agent": "okhttp/3.10.0.1",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "close"
}

SRC_DIR = os.path.dirname(__file__)