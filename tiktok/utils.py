import os, re, logging, hashlib, uuid, string, random, ast
import requests

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

USER_AGENTS = ['Mozilla/5.0 (iPhone; CPU iPhone OS 13_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 musical_ly_16.1.0 JsSdk/2.0 NetType/4G Channel/App Store ByteLocale/en Region/US AppSkin/white ByteFullLocale/en WKWebView/1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 musical_ly_16.6.5 JsSdk/2.0 NetType/4G Channel/App Store ByteLocale/en Region/US AppSkin/white ByteFullLocale/en WKWebView/1', 'Mozilla/5.0 (iPad; CPU OS 13_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 musical_ly_16.6.5 JsSdk/2.0 NetType/WIFI Channel/App Store ByteLocale/en Region/US AppSkin/white ByteFullLocale/en WKWebView/1', 'Mozilla/5.0 (Linux; Android 7.0; LGMS210 Build/NRD90U; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/84.0.4147.111 Mobile Safari/537.36 trill_2021606520 JsSdk/1.0 NetType/WIFI Channel/googleplay AppName/musical_ly app_version/16.6.52 ByteLocale/en ByteFullLocale/en Region/US AppSkin/white', 'Mozilla/5.0 (Linux; Android 8.0.0; SM-A520W Build/R16NW; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/84.0.4147.111 Mobile Safari/537.36 trill_2021606520 JsSdk/1.0 NetType/WIFI Channel/googleplay AppName/musical_ly app_version/16.6.52 ByteLocale/en ByteFullLocale/en Region/CA AppSkin/white', 'Mozilla/5.0 (Linux; Android 6.0.1; SM-G532MT Build/MMB29T; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/84.0.4147.105 Mobile Safari/537.36 trill_2021606520 JsSdk/1.0 NetType/WIFI Channel/googleplay AppName/musical_ly app_version/16.6.52 ByteLocale/pt-BR ByteFullLocale/pt-BR Region/BR AppSkin/white', 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 musical_ly_16.6.5 JsSdk/2.0 NetType/4G Channel/App Store ByteLocale/en Region/US AppSkin/white ByteFullLocale/en WKWebView/1', 'Mozilla/5.0 (Linux; Android 10; SM-G975F Build/QP1A.190711.020; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/84.0.4147.111 Mobile Safari/537.36 trill_2021606520 JsSdk/1.0 NetType/WIFI Channel/googleplay AppName/musical_ly app_version/16.6.52 ByteLocale/en ByteFullLocale/en Region/OM AppSkin/white', 'Mozilla/5.0 (Linux; Android 9; R15_PRO Build/PPR1.180610.011; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/84.0.4147.111 Mobile Safari/537.36 trill_2021702040 JsSdk/1.0 NetType/WIFI Channel/googleplay AppName/musical_ly app_version/17.2.4 ByteLocale/es ByteFullLocale/es Region/ES', 'Mozilla/5.0 (Linux; Android 9; SM-G950U Build/PPR1.180610.011; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/84.0.4147.111 Mobile Safari/537.36 trill_2021606520 JsSdk/1.0 NetType/WIFI Channel/googleplay AppName/musical_ly app_version/16.6.52 ByteLocale/en ByteFullLocale/en Region/US AppSkin/white', 'Mozilla/5.0 (Linux; Android 9; Redmi Note 8T Build/PKQ1.190616.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/84.0.4147.111 Mobile Safari/537.36 trill_2021702040 JsSdk/1.0 NetType/WIFI Channel/googleplay AppName/musical_ly app_version/17.2.4 ByteLocale/es ByteFullLocale/es Region/ES', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.97 Safari/537.36', 'Mozilla/5.0 (Linux; Android 9; SM-J260AZ Build/PPR1.180610.011; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/84.0.4147.105 Mobile Safari/537.36 trill_2021606520 JsSdk/1.0 NetType/WIFI Channel/googleplay AppName/musical_ly app_version/16.6.52 ByteLocale/en ByteFullLocale/en Region/US AppSkin/white', 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 musical_ly_16.6.4 JsSdk/2.0 NetType/4G Channel/App Store ByteLocale/en Region/US AppSkin/white ByteFullLocale/en WKWebView/1', 'Mozilla/5.0 (iPad; CPU OS 13_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 musical_ly_16.6.5 JsSdk/2.0 NetType/WIFI Channel/App Store ByteLocale/en Region/GB AppSkin/white ByteFullLocale/en WKWebView/1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 12_4_8 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 musical_ly_16.6.5 JsSdk/2.0 NetType/WIFI Channel/App Store ByteLocale/en Region/US AppSkin/white ByteFullLocale/en WKWebView/1', 'Mozilla/5.0 (iPad; CPU OS 13_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 musical_ly_16.6.5 JsSdk/2.0 NetType/WIFI Channel/App Store ByteLocale/en Region/US AppSkin/white ByteFullLocale/en WKWebView/1', 'Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3694.0 Mobile Safari/537.36 Chrome-Lighthouse', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.61 Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 musical_ly_16.6.5 JsSdk/2.0 NetType/WIFI Channel/App Store ByteLocale/en Region/US AppSkin/white ByteFullLocale/en WKWebView/1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 musical_ly_16.6.5 JsSdk/2.0 NetType/WIFI Channel/App Store ByteLocale/en Region/US AppSkin/white ByteFullLocale/en WKWebView/1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 musical_ly_16.6.5 JsSdk/2.0 NetType/WIFI Channel/App Store ByteLocale/es Region/ES AppSkin/white ByteFullLocale/es WKWebView/1', 'Mozilla/5.0 (Linux; Android 8.1.0; SM-J727T Build/M1AJQ; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/84.0.4147.105 Mobile Safari/537.36 trill_2021606520 JsSdk/1.0 NetType/WIFI Channel/googleplay AppName/musical_ly app_version/16.6.52 ByteLocale/en ByteFullLocale/en Region/US AppSkin/white', 'Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.0)', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.105 Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 12_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 musical_ly_16.6.5 JsSdk/2.0 NetType/WIFI Channel/App Store ByteLocale/en Region/US AppSkin/white ByteFullLocale/en WKWebView/1', 'Mozilla/5.0 (Linux; Android 8.1.0; SM-G610F Build/M1AJQ; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/84.0.4147.111 Mobile Safari/537.36 trill_2021606520 JsSdk/1.0 NetType/WIFI Channel/googleplay AppName/musical_ly app_version/16.6.52 ByteLocale/es ByteFullLocale/es Region/EC AppSkin/white', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.86 Safari/537.36', 'Mozilla/5.0 (Linux; Android 10; SM-A107M Build/QP1A.190711.020; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/84.0.4147.111 Mobile Safari/537.36 trill_2021606520 JsSdk/1.0 NetType/WIFI Channel/googleplay AppName/musical_ly app_version/16.6.52 ByteLocale/es ByteFullLocale/es Region/CL AppSkin/white', 'Mozilla/5.0 (iPad; CPU OS 13_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 musical_ly_16.6.5 JsSdk/2.0 NetType/WIFI Channel/App Store ByteLocale/en Region/US AppSkin/white ByteFullLocale/en WKWebView/1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_1_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 musical_ly_16.6.5 JsSdk/2.0 NetType/WIFI Channel/App Store ByteLocale/es Region/US AppSkin/white ByteFullLocale/es WKWebView/1', 'Mozilla/5.0 (Linux; Android 9; moto g(6) Build/PDS29.118-15-11-14; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/84.0.4147.111 Mobile Safari/537.36 trill_2021606520 JsSdk/1.0 NetType/WIFI Channel/googleplay AppName/musical_ly app_version/16.6.52 ByteLocale/en ByteFullLocale/en Region/US AppSkin/white', 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 musical_ly_16.6.5 JsSdk/2.0 NetType/WIFI Channel/App Store ByteLocale/en Region/US AppSkin/white ByteFullLocale/en WKWebView/1']

def create_folder(foldername):
    if not os.path.isdir(foldername):
        os.makedirs(foldername)

def generate_device_id():
    # volatile_seed = "12345"
    m = hashlib.md5()
    m.update(generate_UUID(True).encode('utf-8'))
    return m.hexdigest()[:16]

def generate_random():
	return generate_device_id()

def generate_UUID(type):
    generated_uuid = str(uuid.uuid4())
    if (type):
        return generated_uuid
    else:
        return generated_uuid.replace('-', '')

def xorEncrypt(data, key=5):
    xored = [b'%c' % (ord(x) ^ key) for x in data]
    return ''.join([c.hex() for c in xored])

def message_digest(data):
    if not type(data) is bytes:
        data = data.encode()
    return hashlib.md5(data).hexdigest()

def cookies_string(cookies_dict):
    return ''.join('{}={}; '.format(key, val) for key, val in cookies_dict.items()).strip('; ')

def username_to_id(username):
	"""
	:username: tiktok username
	:returns: dict with user_id and user_sec_id
	:throws: error
	"""
	url = 'https://www.tiktok.com/@%s' %username.strip('@')
	headers = headers={
		'User-Agent': random.choice(USER_AGENTS)
	}
	proxy = {
		
	}

	counter = 0
	while True:
		try:
			res = requests.get(url, headers=headers, proxies=proxy, timeout=30)
			if res.status_code == 404:
				raise ValueError('%s not exist' %username)
		except requests.exceptions.RequestException:
			counter += 1
			if counter > 4:
				raise
		else:
			if '"statusCode":10000' in res.text:
				counter += 1
				if counter > 4:
					raise ValueError('Failed to scrape %s id and sec_id' %username)
				headers['User-Agent'] = random.choice(USER_AGENTS)
				# print(counter, res.text)
			else:
				break

	patter = re.compile(r'"userid":[^},]{3,100}', re.IGNORECASE)
	user_id = patter.search(res.text)
	if not user_id:
		patter = re.compile(r'"id":[^},]{3,100}', re.IGNORECASE)
		user_id = patter.search(res.text)

	patter = re.compile(r'"secuid":[^},]{3,100}', re.IGNORECASE)
	sec_user_id = patter.search(res.text)

	if not user_id and not sec_user_id:
		# print(res.text)
		raise ValueError('Failed to scrape %s id and sec_id' %username)
		# print('Failed to scrape %s id and sec_id' %username)
		# return res

	return (
		user_id.group().split(':')[-1].strip('"'),
		sec_user_id.group().split(':')[-1].strip('"')
	)

def rand_mac():
    return "%02x:%02x:%02x:%02x:%02x:%02x" % (
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255)
        )

def random_device():
	device = [part.strip() for part in random.choice(DEVICES).split(';')]
	os_api = device[0].split('/')[0]
	os_version = device[0].split('/')[1][:3]
	dpi = device[1].strip('dpi')
	resolution = device[2]
	brand = device[3].split('/')[-1]
	model = device[4]
	cpu_abi = random.choice(("arm64-v8a", "armeabi-v7a"))
	rom_version = device[-1].strip()

	return {
		'brand': brand,
		'model': model,
		'resolution': resolution,
		'cpu_abi': cpu_abi,
		'os_version': os_version,
		'os_api': os_api,
		'dpi': dpi,
		'rom_version': rom_version,
		'mc': rand_mac(),
		'carrier': random.choice(CARRIERS)
	}

def to_device_string(device_dict):
	if not device_dict:
		return ''
	return '{};{};{};{};{};{};{};{};{};{}'.format(
		device_dict['brand'], device_dict['model'], device_dict['resolution'],
		device_dict['cpu_abi'], device_dict['os_version'], device_dict['os_api'], 
		device_dict['dpi'], device_dict['rom_version'], device_dict['mc'], device_dict['carrier']
	)

def to_device_dict(device_str):
	if not device_str:
		return {}
	device_dict = device_str.split(';')

	if len(device_dict) == 7:
		# old format
		device_dict = dict(zip(['brand', 'model', 'resolution', 'cpu_abi', 'os_version', 'os_api', 'rom_version'], device_dict))
		device_dict['dpi'] = '560'
		device_dict['carrier'] = ['312', '530', 'Sprint Spectrum']
	elif len(device_dict) == 9:
		device_dict = dict(
			zip(['brand', 'model', 'resolution', 'cpu_abi', 'os_version', 'os_api', 'dpi', 'rom_version', 'carrier'], 
			device_dict)
		)
		device_dict['carrier'] = ast.literal_eval(str(device_dict['carrier']))
	elif len(device_dict) == 10:
		device_dict = dict(
			zip(['brand', 'model', 'resolution', 'cpu_abi', 'os_version', 'os_api', 'dpi', 'rom_version', 'mc', 'carrier'], 
			device_dict)
		)
		device_dict['carrier'] = ast.literal_eval(str(device_dict['carrier']))
	else:
		logger.info('invalid device string')
		return ''
	return device_dict
    
def setup_logger(file_name, logger, propagate=False, level=None):
    formatter = logging.Formatter(
        '%(asctime)s - (%(name)s %(threadName)s)  - %(levelname)s - %(message)s', datefmt='%m/%d/%Y %I:%M:%S%p'
    )
    handler = logging.FileHandler(f'logs\\{file_name}', encoding='utf-8')

    if not level:
        handler.setLevel(logging.DEBUG)
    else:
        handler.setLevel(logging.INFO)
        
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = propagate


DEVICES = [
	'28/9; 560dpi; 1440x2621; Google/google; Pixel 3 XL; crosshatch; crosshatch; en_US; Build/PD1A.180720.031',
	'24/7; 480dpi; 1080x1920; Xiaomi/xiaomi; Redmi Note 4; mido; qcom; en_US; Build/NRD90M',
	'23/6; 480dpi; 1080x1920; Xiaomi; Redmi Note 4; nikel; mt6797; en_US; Build/MRA58K',
	'25/7; 320dpi; 720x1280; Xiaomi; Redmi 4X; santoni; qcom; en_US; Build/N2G47H',
	'26/8; 480dpi; 1080x2076; samsung; SM-G950F; dreamlte; samsungexynos8895; en_US; Build/R16NW',
	'26/8; 420dpi; 1080x1920; samsung; SM-A520F; a5y17lte; samsungexynos7880; en_US; Build/R16NW',
	'24/7; 480dpi; 1080x1920; samsung; SM-A520F; a5y17lte; samsungexynos7880; en_US; Build/NRD90M',
	'24/7; 480dpi; 1080x1920; samsung; SM-A510F; a5xelte; samsungexynos7580; en_US; Build/NRD90M',
	'26/8; 480dpi; 1080x1920; HUAWEI/HONOR; STF-L09; HWSTF; hi3660; en_US; Build/HUAWEISTF-L09',
	'26/8; 480dpi; 1080x2032; HUAWEI/HONOR; LLD-L31; HWLLD-H; hi6250; en_US; Build/HONORLLD-L31',
	'26/8; 560dpi; 1440x2792; samsung; SM-G955F; dream2lte; samsungexynos8895; en_US; Build/R16NW',
	'27/8; 440dpi; 1080x2030; Xiaomi/xiaomi; Redmi Note 5; whyred; qcom; en_US; Build/OPM1.171019.011',
	'27/8; 480dpi; 1080x2150; HUAWEI/HONOR; COL-L29; HWCOL; kirin970; en_US; Build/HUAWEICOL-L29',
	'27/8; 480dpi; 1080x1920; Xiaomi/xiaomi; Mi A1; tissot_sprout; qcom; en_US; Build/OPM1.171019.026',
	'26/8; 480dpi; 1080x1920; samsung; SM-G930F; herolte; samsungexynos8890; en_GB; Build/R16NW',
	'26/8; 640dpi; 1440x2560; samsung; SM-G930F; herolte; samsungexynos8890; en_US; Build/R16NW',
	'26/8; 480dpi; 1080x1920; Xiaomi; MI 5; gemini; qcom; en_US; Build/OPR1.170623.032',
	'25/7; 320dpi; 720x1344; Xiaomi; Redmi 5; rosy; qcom; en_US; Build/N2G47H',
	'26/8; 480dpi; 1080x2150; HUAWEI; ANE-LX1; HWANE; hi6250; en_US; Build/HUAWEIANE-LX1',
	'26/8; 420dpi; 1080x2094; samsung; SM-G965F; star2lte; samsungexynos9810; en_US; Build/R16NW',
	'26/8; 560dpi; 1440x2792; samsung; SM-G965F; star2lte; samsungexynos9810; en_US; Build/R16NW',
	'26/8; 480dpi; 1080x1920; samsung; SM-G935F; hero2lte; samsungexynos8890; en_US; Build/R16NW',
	'26/8; 640dpi; 1440x2560; samsung; SM-G935F; hero2lte; samsungexynos8890; en_US; Build/R16NW',
	'24/7; 320dpi; 720x1280; samsung; SM-A310F; a3xelte; samsungexynos7580; en_US; Build/NRD90M',
	'25/7; 440dpi; 1080x2030; Xiaomi/xiaomi; Redmi 5 Plus; vince; qcom; en_US; Build/N2G47H',
	'27/8; 440dpi; 1080x2030; Xiaomi/xiaomi; Redmi 5 Plus; vince; qcom; en_US; Build/OPM1.171019.019',
	'23/6; 480dpi; 1080x1920; Xiaomi; Redmi 4; markw; qcom; en_US; Build/MMB29M',
	'25/7; 320dpi; 720x1280; Xiaomi; Redmi 4A; rolex; qcom; en_US; Build/N2G47H',
	'26/8; 480dpi; 1080x1920; Xiaomi; MI 6; sagit; qcom; en_US; Build/OPR1.170623.027',
	'26/8; 480dpi; 1080x1794; HUAWEI/HONOR; PRA-TL10; HWPRA-H; hi6250; en_US; Build/HONORPRA-TL10',
	'26/8; 320dpi; 720x1280; samsung; SM-J330F; j3y17lte; samsungexynos7570; en_US; Build/R16NW',
	'24/7; 320dpi; 720x1280; samsung; SM-J710F; j7xelte; samsungexynos7870; en_US; Build/NRD90M',
	'24/7; 640dpi; 1440x2560; samsung; SM-G920F; zeroflte; samsungexynos7420; en_US; Build/NRD90M',
	'24/7; 420dpi; 1080x1920; samsung; SM-J730FM; j7y17lte; samsungexynos7870; en_US; Build/NRD90M',
	'24/7; 640dpi; 1440x2560; samsung; SM-G925F; zerolte; samsungexynos7420; en_US; Build/NRD90M',
	'25/7; 320dpi; 720x1280; samsung; SM-J510FN; j5xnlte; qcom; en_US; Build/NMF26X',
	'23/6; 320dpi; 720x1280; Xiaomi; Redmi 3S; land; qcom; en_US; Build/MMB29M',
	'26/8; 320dpi; 720x1280; samsung; SM-A320F; a3y17lte; samsungexynos7870; en_US; Build/R16NW',
	'24/7; 480dpi; 1080x1794; HUAWEI/HONOR; FRD-L09; HWFRD; hi3650; en_US; Build/HUAWEIFRD-L09;',
	'26/8; 420dpi; 1080x1920; samsung; SM-A720F; a7y17lte; samsungexynos7880; en_US; Build/R16NW',
	'26/8; 480dpi; 1080x2076; samsung; SM-A530F; jackpotlte; samsungexynos7885; en_US; Build/R16NW',
	'23/6; 480dpi; 1080x1920; Xiaomi; Redmi Note 3; kenzo; qcom; en_US; Build/MMB29M',
	'24/7; 320dpi; 720x1208; HUAWEI/HONOR; DLI-TL20; HWDLI-Q; qcom; en_US; Build/HONORDLI-TL20',
	'26/8; 480dpi; 1080x2032; HUAWEI; FIG-LX1; HWFIG-H; hi6250; en_US; Build/HUAWEIFIG-LX1',
	'25/7; 320dpi; 720x1280; Xiaomi/xiaomi; Redmi Note 5A; ugglite; qcom; en_US; Build/N2G47H',
	'26/8; 480dpi; 1080x1794; HUAWEI; WAS-LX1; HWWAS-H; hi6250; en_US; Build/HUAWEIWAS-LX1',
	'24/7; 320dpi; 720x1280; samsung; SM-G570F; on5xelte; samsungexynos7570; en_US; Build/NRD90M',
	'25/7; 440dpi; 1080x1920; Xiaomi; MI MAX 2; oxygen; qcom; en_US; Build/NMF26F',
	'26/8; 480dpi; 1080x2076; samsung; SM-G960F; starlte; samsungexynos9810; en_US; Build/R16NW',
	'24/7; 480dpi; 1080x1812; HUAWEI/HONOR; NEM-L51; HNNEM-H; hi6250; en_US; Build/R16NW',
	'24/7; 480dpi; 1080x1920; Xiaomi; MI 5s; capricorn; qcom; en_US; Build/NRD90M',
	'26/8; 420dpi; 1080x2094; samsung; SM-N950F; greatlte; samsungexynos8895; en_US; Build/R16NW',
	'27/8; 320dpi; 720x1280; samsung; SM-J530FM; j5y17lte; samsungexynos7870; en_US; Build/M1AJQ',
	'26/8; 480dpi; 1080x2038; HUAWEI/HONOR; BND-L21; HWBND-H; hi6250; en_US; Build/HONORBND-L21',
	'26/8; 420dpi; 1080x2094; samsung; SM-A730F; jackpot2lte; samsungexynos7885; en_US; Build/R16NW',
	'24/7; 320dpi; 720x1208; HUAWEI; JMM-L22; HWJMM; mt6755; en_US; Build/HUAWEIJMM-L22',
	'25/7; 440dpi; 1080x1920; Xiaomi; Mi Note 3; jason; qcom; en_US; Build/NMF26X',
	'25/7; 320dpi; 720x1280; Xiaomi; Redmi 5A; riva; qcom; en_US; Build/N2G47H',
	'26/8; 480dpi; 1080x2076; samsung; SM-G950U; dreamqltesq; qcom; en_US; Build/R16NW',
	'24/7; 480dpi; 1080x1794; HUAWEI/HONOR; FRD-L19; HWFRD; hi3650; en_US; Build/HUAWEIFRD-L19',
	'27/8; 420dpi; 1080x1920; OnePlus; ONEPLUS A5000; OnePlus5; qcom; en_US; Build/OPM1.171019.011',
	'25/7; 320dpi; 720x1280; Xiaomi/xiaomi; Redmi Note 5A Prime; ugg; qcom; en_US; Build/N2G47H',
	'23/6; 320dpi; 720x1280; samsung; SM-A500F; a5lte; qcom; en_US; Build/MMB29M',
	'26/8; 480dpi; 1080x2040; HUAWEI; RNE-L21; HWRNE; hi6250; en_US; Build/HUAWEIRNE-L21',
	'24/7; 480dpi; 1080x1812; HUAWEI; HUAWEI VNS-L21; HWVNS-H; hi6250; en_US; Build/HUAWEIVNS-L21',
	'26/8; 480dpi; 1080x1920; HUAWEI; VTR-L29; HWVTR; hi3660; en_US; Build/HUAWEIVTR-L29',
	'26/8; 320dpi; 720x1358; HUAWEI/HONOR; AUM-L41; HWAUM-Q; qcom; en_US; Build/HONORAUM-L41',
	'26/8; 480dpi; 1080x1788; HUAWEI; PIC-LX9; HWPIC; hi6250; en_US; Build/HUAWEIPIC-LX9',
	'26/8; 320dpi; 720x1358; HUAWEI/HONOR; AUM-L29; HWAUM-Q; qcom; en_US; Build/HONORAUM-L29',
	'26/8; 420dpi; 1080x2094; samsung; SM-G955U; dream2qltesq; qcom; en_US; Build/R16NW',
	'24/7; 320dpi; 720x1184; asus; ASUS_X008D; ASUS_X008; mt6735; en_US; Build/NRD90M',
	'26/8; 320dpi; 720x1384; samsung; SM-A600FN; a6lte; samsungexynos7870; en_US; Build/R16NW',
	'23/6; 320dpi; 720x1193; LGE/lge; LG-K220; mk6p; mk6p; en_US; Build/MXB48T',
	'26/8; 420dpi; 1080x2094; samsung; SM-A605FN; a6plte; qcom; en_US; Build/R16NW',
	'24/7; 480dpi; 1080x1812; HUAWEI/HONOR; BLN-L21; HWBLN-H; hi6250; en_US; Build/HONORBLN-L21',
	'23/6; 240dpi; 540x960; samsung; SM-G532F; grandpplte; mt6735; en_US; Build/MMB29T',
	'27/8; 320dpi; 720x1280; HMD Global/Nokia; TA-1053; ND1; qcom; en_US; Build/OPR1.170623.026',
	'24/7; 320dpi; 720x1280; samsung; SM-J701F; j7velte; samsungexynos7870; en_US; Build/NRD90M',
	'26/8; 420dpi; 1080x2094; samsung; SM-N950U; greatqlte; qcom; en_US; Build/R16NW',
	'26/8; 420dpi; 1080x2094; samsung; SM-G965U; star2qltesq; qcom; en_US; Build/R16NW',
	'23/6; 320dpi; 720x1208; HUAWEI; DIG-L21HN; HWDIG-L8940; qcom; en_US; Build/HUAWEIDIG-L21HN',
	'26/8; 480dpi; 1080x2076; samsung; SM-G960U; starqltesq; qcom; en_US; Build/R16NW',
	'24/7; 320dpi; 720x1184; Sony; F3112; F3112; mt6755; en_US; Build/33.3.A.1.97',
	'26/8; 480dpi; 1080x2038; HUAWEI; FLA-LX1; HWFLA-H; hi6250; en_US; Build/HUAWEIFLA-LX1',
]

DEVICES2 = [
	'26/7; 560dpi; 1440x2621; Google/google; Pixel 2 XL; crosshatch; crosshatch; en_US; Build/PD1A.180720.031',
	'27/8; 560dpi; 1440x2621; Google/google; Pixel 2 XL; crosshatch; crosshatch; en_US; Build/PD1A.180720.031',
	'28/9; 560dpi; 1440x2621; Google/google; Pixel 2 XL; crosshatch; crosshatch; en_US; Build/PD1A.180720.031',
	'29/10; 560dpi; 1440x2621; Google/google; Pixel 2 XL; crosshatch; crosshatch; en_US; Build/PD1A.180720.031',
	# '24/7; 480dpi; 1080x1920; Google/google; Pixel 2; mido; qcom; en_US; Build/NRD90M',
	# '29/10; 480dpi; 1080x1920; Google/google; Pixel 2; nikel; mt6797; en_US; Build/MRA58K',
	# '25/7; 320dpi; 720x1280; Google/google; Pixel 2; santoni; qcom; en_US; Build/N2G47H',
	# '26/8; 480dpi; 1080x2076; Google/google; Pixel 2; dreamlte; samsungexynos8895; en_US; Build/R16NW',
	# '26/8; 420dpi; 1080x1920; Google/google; Pixel 2; a5y17lte; samsungexynos7880; en_US; Build/R16NW',
	# '29/10; 480dpi; 1080x1920; Google/google; Pixel 2; a5y17lte; samsungexynos7880; en_US; Build/NRD90M',
	# '24/7; 480dpi; 1080x1920; Google/google; Pixel 2; a5xelte; samsungexynos7580; en_US; Build/NRD90M',
	# '26/8; 480dpi; 1080x1920; Google/google; Pixel 2; HWSTF; hi3660; en_US; Build/HUAWEISTF-L09',
	# '26/8; 480dpi; 1080x2032; Google/google; Pixel 2; HWLLD-H; hi6250; en_US; Build/HONORLLD-L31',
	# '26/8; 560dpi; 1440x2792; Google/google; Pixel 2; dream2lte; samsungexynos8895; en_US; Build/R16NW',
	# '27/8; 440dpi; 1080x2030; Google/google; Pixel 2; whyred; qcom; en_US; Build/OPM1.171019.011',
	# '29/10; 480dpi; 1080x2150; Google/google; Pixel 2; HWCOL; kirin970; en_US; Build/HUAWEICOL-L29',
	# '27/8; 480dpi; 1080x1920; Google/google; Pixel 2; tissot_sprout; qcom; en_US; Build/OPM1.171019.026',
	# '26/8; 480dpi; 1080x1920; Google/google; Pixel 2; herolte; samsungexynos8890; en_GB; Build/R16NW',
	# '26/8; 640dpi; 1440x2560; Google/google; Pixel 2; herolte; samsungexynos8890; en_US; Build/R16NW',
	# '26/8; 480dpi; 1080x1920; Google/google; Pixel 2; gemini; qcom; en_US; Build/OPR1.170623.032',
	# '25/7; 320dpi; 720x1344; Google/google; Pixel 2; rosy; qcom; en_US; Build/N2G47H',
	# '26/8; 480dpi; 1080x2150; Google/google; Pixel 2; HWANE; hi6250; en_US; Build/HUAWEIANE-LX1',
]

CARRIERS = [
	["312", "530", "Sprint Spectrum"],
	["310", "120", "Sprint Spectrum"],
	["316", "010", "Sprint Spectrum"],
	["312", "190", "Sprint Spectrum"],
	["311", "880", "Sprint Spectrum"],
	["311", "870", "Sprint Spectrum"],
	["311", "490", "Sprint Spectrum"],
	["310", "160", "T-Mobile"],
	["310", "240", "T-Mobile"],
	["310", "660", "T-Mobile"],
	["310", "230", "T-Mobile"],
	["310", "31", "T-Mobile"],
	["310", "220", "T-Mobile"],
	["310", "270", "T-Mobile"],
	["310", "210", "T-Mobile"],
	["310", "260", "T-Mobile"],
	["310", "200", "T-Mobile"],
	["310", "250", "T-Mobile"],
	["310", "300", "T-Mobile"],
	["310", "280", "T-Mobile"],
	["310", "330", "T-Mobile"],
	["310", "800", "T-Mobile"],
	["310", "310", "T-Mobile"],
	["310", "012", "Verizon Wireless"],
	["311", "280", "Verizon Wireless"],
	["311", "485", "Verizon Wireless"],
	["311", "110", "Verizon Wireless"],
	["311", "285", "Verizon Wireless"],
	["311", "274", "Verizon Wireless"],
	["311", "390", "Verizon Wireless"],
	["310", "010", "Verizon Wireless"],
	["311", "279", "Verizon Wireless"],
	["311", "484", "Verizon Wireless"],
	["310", "910", "Verizon Wireless"],
	["311", "284", "Verizon Wireless"],
	["311", "489", "Verizon Wireless"],
	["311", "273", "Verizon Wireless"],
	["311", "289", "Verizon Wireless"],
	["310", "004", "Verizon Wireless"],
	["311", "278", "Verizon Wireless"],
	["311", "483", "Verizon Wireless"],
	["310", "890", "Verizon Wireless"],
	["311", "283", "Verizon Wireless"],
	["311", "488", "Verizon Wireless"],
	["311", "272", "Verizon Wireless"],
	["311", "288", "Verizon Wireless"],
	["311", "277", "Verizon Wireless"],
	["311", "482", "Verizon Wireless"],
	["310", "590", "Verizon Wireless"],
	["311", "282", "Verizon Wireless"],
	["311", "487", "Verizon Wireless"],
	["311", "271", "Verizon Wireless"],
	["311", "287", "Verizon Wireless"],
	["311", "276", "Verizon Wireless"],
	["311", "481", "Verizon Wireless"],
	["310", "013", "Verizon Wireless"],
	["311", "281", "Verizon Wireless"],
	["311", "486", "Verizon Wireless"],
	["311", "270", "Verizon Wireless"],
	["311", "286", "Verizon Wireless"],
	["311", "275", "Verizon Wireless"],
	["311", "480", "Verizon Wireless"],
	["310", "560", "AT&T Wireless Inc."],
	["310", "410", "AT&T Wireless Inc."],
	["310", "380", "AT&T Wireless Inc."],
	["310", "170", "AT&T Wireless Inc."],
	["310", "150", "AT&T Wireless Inc."],
	["310", "680", "AT&T Wireless Inc."],
	["310", "070", "AT&T Wireless Inc."],
	["310", "980", "AT&T Wireless Inc."]
]


if __name__ == '__main__':
	pass
