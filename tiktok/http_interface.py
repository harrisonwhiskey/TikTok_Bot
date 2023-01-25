import requests
import time
import logging
from concurrent import futures
from urllib.parse import urlencode
from urllib3.exceptions import InsecureRequestWarning

from .xgorgon import x_gorgon_wrapper
from .utils import message_digest, cookies_string, setup_logger
from .error import TikTokException

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

error_logger = logging.getLogger('http_error')
error_logger.setLevel(logging.DEBUG)
setup_logger('http_error.log', error_logger)

# Suppress only the single warning from urllib3 needed.
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

def wrap(arg):
    return x_gorgon_wrapper(arg[0], arg[1])


class http:
    def __init__(self, tiktok_session):
        self._parent = tiktok_session
        self._HTTP_session = requests.Session()

    def send_request(self, api, method):
        url = self._full_url(api.url, api.params)

        if not api.skip:
            ts = int(time.time())
            a2 = message_digest(self._query_string(url))

            if api.get_posts() and api.encoding != 'image_upload':
                str4 = message_digest(api.get_body()).upper()
                api.add_header('X-SS-STUB', str4)
            else:
                str4 = "00000000000000000000000000000000"
            str4 = str5 = str6 = "00000000000000000000000000000000"
            data = '{}{}{}{}'.format(a2, str4, str5, str6)

            args = ((ts, data), )
            # x_gorgon = X_Gorgon(ts, data)
            # old_time = time.time()

            with futures.ProcessPoolExecutor(max_workers=1) as executor:
                result = executor.map(wrap, args)
                x_gorgon = list(result)[0]

            # old_time = time.time() - old_time
            # if old_time >= 0.8:
            #     print('x_gorgon took: %s' %(old_time))
            (
                api.add_header('X-Gorgon', x_gorgon)
                .add_header('X-Khronos', str(ts))
                .add_header('sdk-version', '1')
                .add_header('Cookie', cookies_string(self._parent.settings.get_cookies()))
                .add_header('X-Tt-Token', self._parent.settings.get('X-Tt-Token'))
            )

            if 'x-common-params-v2' in api.headers:
                # add default params as headers
                api.add_header('x-common-params-v2', urlencode(
                    {k: v for k, v in api.default_params.items() if k not in api.params}))

        if api.get_posts():
            if api.encoding == 'urlencode':
                api.add_header(
                    'Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8')
            elif api.encoding == 'protobuf':
                api.add_header('Content-Type', 'application/x-protobuf')
            elif api.encoding == 'image_upload':
                api.add_header('Content-Type', api.get_body().content_type)
            else:
                api.add_header('Content-Type', 'application/json')

        self._HTTP_session.headers.update(api.headers)

        # logger.debug('Headers -> %s' % self._HTTP_session.headers)
        logger.debug('URL -> %s. Body -> %s' % (url, api.get_body()))

        error_counter = 0
        while True:
            try:
                if method == 'get':
                    response = self._HTTP_session.request(
                        method, url, proxies=self._proxy, timeout=60, verify=False)
                elif method == 'post':
                    response = self._HTTP_session.request(
                        method, url, proxies=self._proxy, data=api.get_body(), timeout=60, verify=False)
                break
            except (requests.exceptions.RequestException, requests.exceptions.ProxyError) as e:
                logger.error('Proxy/ConnectionError error (%s): %s' %(error_counter, e))
                error_counter += 1
                if error_counter > 5:
                    raise
                time.sleep(max(error_counter, 1) * 5)

        if response.status_code != 200:
            error_logger.error('Status: %s -> %s' %(response.status_code, response.content))
            error_logger.debug('Headers -> %s' % self._HTTP_session.headers)
            error_logger.debug('URL -> %s Body -> %s' % (url, api.get_body()))
                
            raise TikTokException('Connection error!!. Check error log')

        self._save_cookies()
        return response

    def _full_url(self, url, params):
        if params:
            url = '{}?{}'.format(url, urlencode(params))
            if url.endswith('%26'):
                return url[:-3] + '&'

        return url

    def _query_string(self, url):
        idx = url.index('?')
        return url[idx+1:]

    def _save_cookies(self):
        for c in self._HTTP_session.cookies:
            self._parent.settings.set_cookie(c.name, c.value)

    def get_x(self, t, a2):
        a2 = message_digest(a2)
        str4 = str5 = str6 = "00000000000000000000000000000000"
        x_gorgon = x_gorgon_wrapper(t, a2 + str4 + str5 + str6)
        return x_gorgon
    
    @property
    def _proxy(self):
        """
        192.3.1.2:8080,username,password
        """
        proxy = self._parent.proxy

        if not proxy:
            return None

        proxies = {}
        proxy = proxy.split(',')
        proxy = [item.strip() for item in proxy]
        if len(proxy) == 1:
            proxies['http'] = proxy[0]
            proxies['https'] = proxy[0]
            # logger.debug('Setting proxy to %s: %s' %(self._parent.proxy, proxies))
        elif len(proxy) == 3:
            proxies['http'] = 'http://{}:{}@{}/'.format(proxy[1], proxy[2], proxy[0])
            proxies['https'] = 'http://{}:{}@{}/'.format(proxy[1], proxy[2], proxy[0])
            # logger.debug('Setting proxy to %s: %s' %(self._parent.proxy, proxies))
        else:
            logger.error('Invalid proxy %s format' %self._parent.proxy)
            return None

        return proxies



if __name__ == '__name__':
    pass
