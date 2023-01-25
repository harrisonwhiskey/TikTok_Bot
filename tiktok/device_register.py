import sys
import json
import os
import logging
import copy
import time
import random
import string
from urllib.parse import urlencode

from frida import get_usb_device

from .utils import generate_UUID, rand_mac
from .constants import SRC_DIR

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Android:
    def __init__(self, data=None):
        with open(os.path.join(SRC_DIR, 'device_register.js'), encoding="utf8") as f:
            js_code = f.read()

        self._received = False
        self.wait_flag = True
        self.results = {}
        self._app_id = 'com.zhiliaoapp.musically'
        res = self.clear_cookies(self._app_id)
        time.sleep(1)
        res = self.clear_cookies(self._app_id)
        logger.info('%s Cookies cleared: %s' % (self._app_id, res))

        pid = get_usb_device(5).spawn(self._app_id)
        session = get_usb_device().attach(pid)
        self._script = session.create_script(js_code)
        self._script.on('message', self._on_message)
        self._script.load()
        get_usb_device().resume(pid)
        logger.info('%s app started' % self._app_id)

        self.time = time.time()
        self._data = data
    
    def clear_cookies(self, app_id):
        adb = '"C:\\Program Files\\Genymobile\\Genymotion\\tools\\adb"'
        return os.popen(adb + ' shell pm clear %s' % app_id).read().strip()

    def _on_message(self, message, data):
        if message['type'] == 'send':
            if  message['payload'] == 'google_aid':
                self._script.post(
                    {"type": "input", "payload": self._data['google_aid']}
                )
            elif message['payload'] == 'openudid':
                self._script.post(
                    {"type": "input", "payload": self._data['openudid']}
                )
            elif message['payload'] == 'uuid':
                self._script.post(
                    {"type": "input", "payload": self._data['uuid']}
                )
            elif message['payload'] == 'data':
                self._script.post(
                    {"type": "input", "payload": json.dumps(self._data)}
                )
            elif 'device_id' in message['payload']:
                # jackpot
                logger.info(message['payload'])
                payload = json.loads(message['payload'])
                self.results['device_id'] = payload['device_id_str']
                self.results['install_id'] = payload['install_id_str']
                self._received = True
                self._finish()
            else:
                logger.error('++++space++++')
                logger.error(message['payload'])
        else:
            # error from js code
            logger.error(message)

    def _finish(self):
        if self._received:
            time.sleep(15)
            # self.clear_cookies(self._app_id)
            self.wait_flag = False


def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%m/%d/%Y %I:%M:%S%p'
    )

    APP_DATA = {
        'update_version_code': 2021407050,
        'version_code': 140705,
        'app_version': "14.7.5",
        'app_key': "5559e28267e58eb4c1000012",
        'release_build': "688b613_20200121",
    }
    device = {
        'brand': 'Xiaomi',
        'model': 'Pixel 2 XL',
        'resolution': '1080x1920',
        'cpu_abi': 'armeabi-v7a',
        'os_version': '6.0',
        'os_api': '23',
        'dpi': '480',
        'rom_version': 'MMB29M',
        'carrier': ['310', '200', 'T-Mobile']
    }

    data = {
        **APP_DATA,
        **device,
        'google_aid': '7ca9e6f3-9427-43d7-a0da-0fb6f8d9b191',
        'openudid': '2b7c4740adabed99'
    }
    return Android(data=data)
