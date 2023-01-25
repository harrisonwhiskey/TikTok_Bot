import time
import json
import logging
import base64
from urllib.parse import urlencode
from requests_toolbelt import MultipartEncoder
from requests.exceptions import RequestException, ProxyError

import requests
import time
from concurrent import futures
from urllib3.exceptions import InsecureRequestWarning

from .error import TikTokException

from .constants import APP_DATA, BASIC_HEADERS
from .utils import generate_UUID, message_digest, cookies_string
from .grpc import message_pb2

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class API:
    def __init__(self, url, tiktok_session):
        self._posts = {}
        self._parent = tiktok_session
        self._disable_default_params = False
        self._is_body = False
        self._HTTP_session = requests.Session()

        self.url = url
        self.params = {}
        self.repeat_params = False
        self.headers = {}
        self.skip = False
        self.encoding = 'json'
        self.default_params = self._generate_default_params()
    

    def add_header(self, key, value):
        if value is not None and value != '':
            self.headers[key] = value
        return self
    
    def add_basic_headers(self):
        self.add_header("User-Agent", "com.zhiliaoapp.musically/2021407050 (Linux; U; Android " + self._parent.device['os_version'] + "; en_US; " + self._parent.device['model'] + "; Build/" + self._parent.device['rom_version'].split('/')[-1] + ")")
        self.add_header("Accept-Encoding", "gzip, deflate")
        return self
    
    def add_param(self, key, value, skip_if_exist=False):
        if skip_if_exist:
            if not key in self.params:
                self.params[key] = value
        else:
            if value is not None:
                self.params[key] = value
        return self

    def set_repeat_params(self, _bool):
        self.repeat_params = _bool
        return self

    def add_post(self, key, value):
        if value is not None:
            self._posts[key] = value
        return self

    def add_posts(self, data_dict):
        self._posts.update(data_dict)
        return self
    
    def get_posts(self):
        return self._posts
    
    def get_body(self):
        if self.encoding == 'json':
            return json.dumps(self.get_posts())
        elif self.encoding == 'urlencode':
            body = urlencode(self.get_posts())
            if '&text_extra=%5B' in body:
                body = body.replace('%27', '')
                body = body.replace('+%7B', '%7B')
            return body
        elif self.encoding == 'image_upload':
            if not self._is_body:
                body = {}
                for k, v in self.default_params.items():
                    body[k] = (None, str(v), 'text/plain; charset=UTF-8', {'Content-Transfer-Encoding':'binary'})
                body['file'] = ('profileHeaderCrop.png', open(self._posts['img_path'], 'rb'), 'application/octet-stream', {'Content-Transfer-Encoding':'binary'})
                self.body = MultipartEncoder(fields=body, boundary=generate_UUID(True))
                self._is_body = True
            return self.body
        elif self.encoding == 'protobuf':
            # request
            request = message_pb2.Request()
            request.cmd = self._posts['cmd']
            request.sequence_id = 803817
            request.sdk_version = "4.0.6.0" 
            request.token = self._parent.settings.get('X-Tt-Token') 
            request.refer = message_pb2.Refer.ANDROID 
            request.inbox_type = 0
            request.build_number = "4060"
            request.body = self._posts['body']
            request.device_id = self._parent.settings.get('device_id') 
            request.channel = "googleplay" 
            request.device_platform = "android" 
            request.device_type = self._parent.device['model'] 
            request.os_version = self._parent.device['os_version'] 
            request.version_code = str(APP_DATA['update_version_code']) 
            # request.headers.update({"iid": self._parent.settings.get('install_id'), "net_mcc_mnc": "310260", "aid": "1233", "sim_mcc_mnc": "310260"})
            return request.SerializeToString()

    def set_encoding(self, encoding):
        self.encoding = encoding
        return self
        
    def set_disable_default_params(self, _bool):
        self._disable_default_params = _bool
        return self
    
    def set_skip(self, _bool):
        self.skip = _bool
        return self
    
    def _add_default_params(self):
       # self.params.update({k:v for k,v in self.default_params.items()})
       self.params.update(self.default_params)
       return self

    def _generate_default_params(self):
        time_stamp = int(round(time.time() * 1000))
        return {
            'os_api': self._parent.device['os_api'],
            'device_type': self._parent.device['model'],
            'ssmix': 'a',
            'manifest_version_code': APP_DATA['update_version_code'],
            'dpi': self._parent.device['dpi'],
            'uoo': '0',
            'carrier_region': 'US',
            'region': 'US',
            'carrier_region_v2': self._parent.device['carrier'][0],
            'app_name': 'musical_ly',
            'version_name': APP_DATA['app_version'],
            'timezone_offset': '0',
            'ts': int(time_stamp / 1000),
            'ab_version': APP_DATA['app_version'],
            'pass-route': '1',
            'pass-region': '1',
            'is_my_cn': '0',
            'ac2': 'wifi',
            'app_type': 'normal',
            'ac': 'wifi',
            'update_version_code': APP_DATA['update_version_code'],
            'channel': 'googleplay',
            '_rticket': time_stamp,
            'device_platform': 'android',
            'iid': self._parent.settings.get('install_id'),
            'build_number': APP_DATA['app_version'],
            'locale': 'en',
            'op_region': 'US',
            'version_code': APP_DATA['version_code'],
            'timezone_name': 'America/New_York',
            'openudid': self._parent.settings.get('openudid'),
            'sys_region': 'US',
            'device_id': self._parent.settings.get('device_id'),
            'app_language': 'en',
            'resolution': '*'.join(self._parent.device['resolution'].split('x')),
            'os_version': self._parent.device['os_version'],
            'language': 'en',
            'device_brand': self._parent.device['brand'],
            'aid': '1233',
            'residence': 'US',
            'current_region': 'US',
            # 'mcc_mnc': self._parent.device['carrier'][0] + self._parent.device['carrier'][1],
        }

    def get_response(self, method):
        self.add_basic_headers()

        if not self._disable_default_params:
            self._add_default_params()

        return self._send_request(method)

    def _send_request(self, method):
        url = self._full_url(self.url, self.params)
        if not self.skip:
            ts = int(time.time())
            x_gorgon = self._get_xgorgon(ts, self._query_string(url))

            if self.get_posts() and self.encoding != 'image_upload':
                # str4 = message_digest(self.get_body()).upper()
                self.add_header('X-SS-STUB', message_digest(self.get_body()).upper())

            (
                self.add_header('X-Gorgon', x_gorgon)
                .add_header('X-Khronos', str(ts))
                .add_header('sdk-version', '1')
                .add_header('Cookie', cookies_string(self._parent.settings.get_cookies()))
                .add_header('X-Tt-Token', self._parent.settings.get('X-Tt-Token'))
            )

            if 'x-common-params-v2' in self.headers:
                # add default params as headers
                self.add_header('x-common-params-v2', urlencode(
                    {k: v for k, v in self.default_params.items() if k not in self.params}))

        if self.get_posts():
            if self.encoding == 'urlencode':
                self.add_header(
                    'Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8')
            elif self.encoding == 'protobuf':
                self.add_header('Content-Type', 'application/x-protobuf')
            elif self.encoding == 'image_upload':
                self.add_header('Content-Type', self.get_body().content_type)
            else:
                self.add_header('Content-Type', 'application/json; charset=utf-8')

        self._HTTP_session.headers.update(self.headers)

        # logger.debug('Headers -> %s' % self._HTTP_session.headers)
        logger.debug('URL -> %s. Body -> %s' % (url, self.get_body()))

        error_counter = 0
        while True:
            try:
                if method == 'get':
                    response = self._HTTP_session.request(
                        method, url, proxies=self._proxy, timeout=60, verify=True)
                elif method == 'post':
                    response = self._HTTP_session.request(
                        method, url, proxies=self._proxy, data=self.get_body(), timeout=60, verify=True)
                break
            except (RequestException, ProxyError) as e:
                logger.error('Proxy/ConnectionError error (%s): %s' %(error_counter, e))
                error_counter += 1
                if '502' in str(e) and error_counter >= 3:
                    raise
                if error_counter > 4:
                    raise
                time.sleep(max(error_counter, 1) * 2)

        if response.status_code != 200:
            # error_logger.error('Status: %s -> %s' %(response.status_code, response.content))
            # error_logger.debug('Headers -> %s' % self._HTTP_session.headers)
            # error_logger.debug('URL -> %s Body -> %s' % (url, api.get_body()))
            raise TikTokException('Connection error!!')

        self._save_cookies()
        return response

    def _full_url(self, url, params):
        if params:
            url = '{}?{}'.format(url, urlencode(params))
            if self.repeat_params:
                url = '{}&{}'.format(url, urlencode(params))
            if url.endswith('%26'):
                return url[:-3] + '&'
        return url

    def _query_string(self, url):
        idx = url.index('?')
        return url[idx+1:]

    def _save_cookies(self):
        for c in self._HTTP_session.cookies:
            self._parent.settings.set_cookie(c.name, c.value)

    def _get_xgorgon(self, ts, url_query):
        a2 = message_digest(url_query)
        str4 = str5 = str6 = "00000000000000000000000000000000"
        data = f'{a2}{str4}{str5}{str6}'

        error_counter = 0
        while True:
            try:
                x_gorgon = requests.post(
                    'http://127.0.0.1:2050/api',
                    json={'secs': ts, 'data': data},
                    timeout=30
                ).json().get('x-kronos')
                break
            except (json.decoder.JSONDecodeError, RequestException, ProxyError):
                error_counter += 1
                if error_counter >= 5:
                    raise
                continue

        if not x_gorgon or 'error' in x_gorgon:
            raise Exception('Failed to get x_gorgon: %s' % x_gorgon)
        return x_gorgon

    @property
    def _proxy(self):
        """
        192.3.1.2:8080,username,password
        """
        proxy = self._parent.proxy
        if not proxy:
            logger.error('NO Proxy!!')
            return None

        proxies = {}
        proxy = proxy.split(',')
        proxy = [item.strip() for item in proxy]
        if len(proxy) == 1:
            proxies['http'] = 'http://{}'.format(proxy[0])
            proxies['https'] = 'http://{}'.format(proxy[0])
            logger.debug('Setting proxy to %s: %s' %(self._parent.proxy, proxies))
        elif len(proxy) == 3:
            proxies['http'] = 'http://{}:{}@{}/'.format(proxy[1], proxy[2], proxy[0])
            proxies['https'] = 'http://{}:{}@{}/'.format(proxy[1], proxy[2], proxy[0])
            logger.debug('Setting proxy to %s: %s' %(self._parent.proxy, proxies))
        else:
            logger.error('Invalid proxy %s format' %self._parent.proxy)
            return None
        return proxies
