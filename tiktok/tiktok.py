import requests
import logging
import time
import json
import cv2
import numpy as np
import random
import base64
from datetime import datetime

from requests import api

from .api import API
from .storage import Storage
from .device_register import Android
from .utils import (
    generate_UUID, generate_device_id, xorEncrypt, cookies_string, username_to_id, random_device,
    to_device_string, to_device_dict, rand_mac, message_digest
)
from .constants import APP_DATA, DEVICE_DATA, TIKTOK_API_19, TIKTOK_API_16, TIKTOK_API, TIKTOK_IM
from .response import (
    LoginResponse, FollowUserResponse, UnFollowUserResponse, LikeVideoResponse, LikeCommentResponse, CommentResponse, UserResponse,
    UploadImageResponse, UserVideoListResponse, FollowersFollowingsResponse, SendSmsCodeResponse,
    SetPasswordResponse, ChangeUsernameResponse, CheckEmailResponse, SendEmailCodeResponse, SendEmailCodeResponse,
    VerifyEmailCodeResponse, CommentSettingsResponse, DeleteVideoResponse, CheckInResponse, ShareResponse, Response
)
import tiktok.error


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def random_numbs(size=15):
    return ''.join(str(random.choice([0,1,2,3,4,5,6,7,8,9])) for _ in range(size))

def pack_string(data):
    byte_arr = bytearray()
    for x in data:
        byte_arr += (ord(x) ^ -99).to_bytes(2, 'little', signed=True)
    return base64.urlsafe_b64encode(byte_arr).decode('utf-8')

class TikTok(object):
    def __init__(self, storage_path=None):
        self.settings = Storage(storage_path)
        self.username = None
        self.pwd = None
        self.device = None
        self.is_logged_in = False
        self.login_flow = True

    def login(self, username, password, email=None, proxy=None, force_login=False, reset_device=False):
        """
        :returns: None when a session is resumed / UserResponse when re-(login) is performed
        :throws: CaptchaErrorException / InvalidAccountException / BadRequestException
        """
        logger.info('%s -> Logging in' % username)
        self.pwd = password
        # switch the currently active user if the details are different
        if username != self.username:
            self._set_user(username, password, reset_device, proxy)
            if email:
                self.settings.set('email', email)
            if proxy != None:
                self.proxy = proxy

        if not self.is_logged_in or force_login:
            logger.info('Performing full login...')
            raise Exception('Account Not Logged in')
            
            # take out login for now
            response = LoginResponse(
                API('%s/passport/user/login/' % TIKTOK_API_19, self)
                .add_param('account_sdk_version', '380')
                .add_post('password', xorEncrypt(password))
                .add_post('account_sdk_source', 'app')
                .add_post('mix_mode', '1')
                .add_post('multi_login', '1')
                .add_post('username', xorEncrypt(username))
                .set_encoding('urlencode')
                .get_response('post')
            )
            if response.status != 'ok':
                try:
                    tiktok.error.throw_exception(
                        response.error_code, response.error_message)
                except tiktok.error.BadRequestException as e:
                    logger.exception(e)
                    # self.settings.set('install_id', '')  # cause device reset
                    raise
            self._update_login_state(response)
            return self._send_login_flow(True)

        if not self.login_flow:
            return
        return self._send_login_flow(False)

    @property
    def proxy(self):
        return self.settings.get('proxy')

    @proxy.setter
    def proxy(self, proxy):
        self.settings.set('proxy', proxy)

    def get_captcha(self):
        """
        returns url of captcha
        """
        logger.debug('getting captcha...')
        response = (
            API('https://verification-va.musical.ly/get', self)
            .set_skip(True)
            .set_disable_default_params(True)
            .add_param('aid', '1233')
            .add_param('lang', 'en')
            .add_param('app_name', 'musical_ly')
            .add_param('iid', self.settings.get('install_id'))
            .add_param('vc', APP_DATA['version_code'])
            .add_param('did', self.settings.get('device_id'))
            .add_param('ch', 'googleplay')
            .add_param('os', '0')
            .add_param('challenge_code', '1105')
            .get_response('get')
        )
        response = response.json()
        if response['msg_type'] == 'error':
            raise tiktok.error.CaptchaErrorException(
                'Failed to download captcha images. -> %s' % response)

        puzzle_url = response['data']['question']['url1']
        piece_url = response['data']['question']['url2']
        tip_y = response['data']['question']['tip_y']
        captcha_id = response['data']['id']

        r = requests.get(puzzle_url, allow_redirects=True)
        open('puzzle_img/puzzle.jpg', 'wb').write(r.content)

        r = requests.get(piece_url, allow_redirects=True)
        open('puzzle_img/piece.jpg', 'wb').write(r.content)

        print('y:', tip_y, '->', tip_y*0.37)
        return (
            response['data']['question']['url1'],
            response['data']['question']['url2'],
            response['data']['question']['tip_y'],
            response['data']['id']
        )

    def solve_captcha_new(self, x_cord, y_cord, captcha_id):
        rand_lenght = random.randint(90, 120)
        reply = [
            {
                "relative_time": (rand_lenght * (x+1)) * 2,
                "x": int(x_cord / (rand_lenght / (x+1))),
                "y": y_cord
            } for x in range(rand_lenght)
        ]
        # time.sleep(random.randint(6, 11))
        response = (
            API('https://verification-va.musical.ly/verify', self)
            .set_skip(True)
            .set_disable_default_params(True)
            .add_param('aid', '1233')
            .add_param('lang', 'en')
            .add_param('app_name', 'musical_ly')
            .add_param('iid', self.settings.get('install_id'))
            .add_param('vc', APP_DATA['update_version_code'])
            .add_param('did', self.settings.get('device_id'))
            .add_param('ch', 'googleplay')
            .add_param('os', '0')
            .add_param('challenge_code', '1105')
            .add_param('os_name', 'Android')
            .add_param('platform', 'app')
            .add_param('webdriver', 'false')
            .add_post('modified_img_width', 260)
            .add_post('id', captcha_id)
            .add_post('mode', 'slide')
            .add_post('reply', reply)
            .add_post('webdriver', 'false')
            .add_post('cid', captcha_id)
            .add_post('os_name', 'Android')
            .add_post('platform', 'app')
            .add_header('Content-Type', 'application/x-www-form-urlencoded')
            .add_header('Cookie', cookies_string(self.settings.get_cookies()))
            .add_header('Referer', 'https://verification-va.musical.ly/view?aid=1233&lang=en&app_name=musical_ly&iid=' + str(self.settings.get('install_id')) + '&vc=2021407050&did=' + str(self.settings.get('device_id')) + '&ch=googleplay&os=0&challenge_code=1105')
            .get_response('post')
        )
        response = response.json()
        if response['msg_type'] == 'success':
            logger.debug('Captcha successfully solved')
            return response
        raise tiktok.error.CaptchaErrorException(
            'Failed to solve captcha -> %s' % response)

    def auto_solve_captcha(self, puzzle_url, piece_url):
        """
        :throws: CaptchaErrorException - When it fails to solve captcha correctly
        :returns: None
        """

        for i in range(3):
            try:
                puzzle = requests.get(puzzle_url, stream=True).raw
            except requests.exceptions.RequestException:
                if i == 2:
                    raise
                time.sleep(3)
        puzzle = np.asarray(bytearray(puzzle.read()), dtype="uint8")
        puzzle = cv2.imdecode(puzzle, cv2.IMREAD_GRAYSCALE)

        for i in range(3):
            try:
                piece = requests.get(piece_url, stream=True).raw
            except requests.exceptions.RequestException as e:
                if i == 2:
                    raise
                # print('%s. Captcha Error: %s' %(i, e))
                time.sleep(3)
        piece = np.asarray(bytearray(piece.read()), dtype="uint8")
        piece = cv2.imdecode(piece, cv2.IMREAD_GRAYSCALE)

        # Store width and height of template in w and h
        # w, h = piece.shape[::-1]

        # Perform match operations.
        res = cv2.matchTemplate(puzzle, piece, cv2.TM_CCOEFF_NORMED)

        # Specify a threshold
        threshold = 0.4

        # Store the coordinates of matched area in a numpy array

        highest_threshold = False
        while True:
            loc = np.where(res >= threshold)
            if len(loc[0]) == 0:
                threshold -= 0.05
                highest_threshold = True
                continue

            if len(loc[0]) == 1:
                break

            if  len(loc[0]) > 0 and highest_threshold:
                raise tiktok.error.CaptchaErrorException(
                    'Failed to to solve captcha puzzle. ')

            threshold += 0.05

        return next(zip(*loc))[1]

    def solve_captcha(self):
        """
        :throws: CaptchaErrorException - When it fails to solve captcha correctly
        :returns: None
        """
        logger.debug('Solving captcha...')
        response = (
            API('https://verification-va.musical.ly/get', self)
            .set_skip(True)
            .set_disable_default_params(True)
            .add_param('aid', '1233')
            .add_param('lang', 'en')
            .add_param('app_name', 'musical_ly')
            .add_param('iid', self.settings.get('install_id'))
            .add_param('vc', APP_DATA['version_code'])
            .add_param('did', self.settings.get('device_id'))
            .add_param('ch', 'googleplay')
            .add_param('os', '0')
            .add_param('challenge_code', '1105')
            .get_response('get')
        )
        response = response.json()
        if response['msg_type'] == 'error':
            raise tiktok.error.CaptchaErrorException(
                'Failed to download captcha images. -> %s' % response)

        puzzle_url = response['data']['question']['url1']
        piece_url = response['data']['question']['url2']
        tip_y = response['data']['question']['tip_y']
        captcha_id = response['data']['id']

        for i in range(3):
            try:
                puzzle = requests.get(puzzle_url, stream=True).raw
            except requests.exceptions.RequestException:
                if i == 2:
                    raise
                time.sleep(3)
        puzzle = np.asarray(bytearray(puzzle.read()), dtype="uint8")
        puzzle = cv2.imdecode(puzzle, cv2.IMREAD_GRAYSCALE)

        for i in range(3):
            try:
                piece = requests.get(piece_url, stream=True).raw
            except requests.exceptions.RequestException as e:
                if i == 2:
                    raise
                # print('%s. Captcha Error: %s' %(i, e))
                time.sleep(3)
        piece = np.asarray(bytearray(piece.read()), dtype="uint8")
        piece = cv2.imdecode(piece, cv2.IMREAD_GRAYSCALE)

        # Store width and height of template in w and h
        # w, h = piece.shape[::-1]

        # Perform match operations.
        res = cv2.matchTemplate(puzzle, piece, cv2.TM_CCOEFF_NORMED)

        # Specify a threshold
        threshold = 0.4

        # Store the coordinates of matched area in a numpy array

        highest_threshold = False
        while True:
            loc = np.where(res >= threshold)
            if len(loc[0]) == 0:
                threshold -= 0.05
                highest_threshold = True
                continue

            if len(loc[0]) == 1:
                break

            if  len(loc[0]) > 0 and highest_threshold:
                raise tiktok.error.CaptchaErrorException(
                    'Failed to to solve captcha puzzle. ')

            threshold += 0.05

        tip_x = next(zip(*loc))[1]

        rand_lenght = random.randint(90, 120)
        reply = [
            {
                "relative_time": (rand_lenght * (x+1)) * 2,
                "x": int(tip_x / (rand_lenght / (x+1))),
                "y": tip_y
            } for x in range(rand_lenght)
        ]
        time.sleep(random.randint(6, 11))
        response = (
            API('https://verification-va.musical.ly/verify', self)
            .set_skip(True)
            .set_disable_default_params(True)
            .add_param('aid', '1233')
            .add_param('lang', 'en')
            .add_param('app_name', 'musical_ly')
            .add_param('iid', self.settings.get('install_id'))
            .add_param('vc', APP_DATA['update_version_code'])
            .add_param('did', self.settings.get('device_id'))
            .add_param('ch', 'googleplay')
            .add_param('os', '0')
            .add_param('challenge_code', '1105')
            .add_param('os_name', 'Android')
            .add_param('platform', 'app')
            .add_param('webdriver', 'false')
            .add_post('modified_img_width', 260)
            .add_post('id', captcha_id)
            .add_post('mode', 'slide')
            .add_post('reply', reply)
            .add_post('webdriver', 'false')
            .add_post('cid', captcha_id)
            .add_post('os_name', 'Android')
            .add_post('platform', 'app')
            .add_header('Content-Type', 'application/x-www-form-urlencoded')
            .add_header('Cookie', cookies_string(self.settings.get_cookies()))
            .add_header('Referer', 'https://verification-va.musical.ly/view?aid=1233&lang=en&app_name=musical_ly&iid=' + str(self.settings.get('install_id')) + '&vc=2021407050&did=' + str(self.settings.get('device_id')) + '&ch=googleplay&os=0&challenge_code=1105')
            .get_response('post')
        )
        response = response.json()
        if response['msg_type'] == 'success':
            logger.debug('Captcha successfully solved')
            return
        raise tiktok.error.CaptchaErrorException(
            'Failed to solve captcha -> %s' % response)

    def follow_by_id(self, user_id=None, sec_id=None):
        """
        follow
        returns: FollowUserResponse
        """
        if not user_id and not sec_id:
            raise TypeError('Provide user user_id or sec_id')

        # official app add these headers and changes based on where you are following
        # user from. still works without or any random numbers.
        # from followers list, from followings list, from profile page
        from_channel_id = random.choice([(11, 26), (10, 10), (0, 3)])
        time_stamp = int(round(time.time() * 1000))

        resp = FollowUserResponse(
            API('%s/aweme/v1/commit/follow/user/' % TIKTOK_API[random.randint(0, 1)], self)
            .set_disable_default_params(True)
            .add_param('user_id', user_id)
            .add_param('sec_user_id', sec_id)
            .add_param('from', from_channel_id[0])
            .add_param('from_pre', -1)
            .add_param('type', 1)
            .add_param('channel_id', from_channel_id[1])
            .add_param('_rticket', time_stamp)
            .add_param('mcc_mnc', self.device['carrier'][0] + self.device['carrier'][1])
            .add_param('carrier_region_v2', self.device['carrier'][0])
            .add_param('op_region', 'US')
            .add_param('ts', '%s&' % int(time_stamp / 1000))
            .add_header('x-common-params-v2', True)
            .get_response('get')
        )
        if resp.status == 'fail':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def follow_by_username(self, username):
        user_id, sec_id = username_to_id(username)
        return self.follow_by_id(user_id=user_id, sec_id=sec_id)

    def unfollow(self, user_id=None, sec_id=None):
        """
        unfollow
        returns: UnFollowUserResponse
        """
        if not user_id and not sec_id:
            raise TypeError('Provide user user_id or sec_id')

        # official app add these headers and changes based on where you are following
        # user from. still works without or any random numbers.
        # from followers list, from followings list, from profile page
        from_channel_id = [(11, 26), (10, 10), (0, 3)]
        from_channel_id = from_channel_id[random.randint(0, 2)]
        time_stamp = int(round(time.time() * 1000))

        resp = UnFollowUserResponse(
            API('%s/aweme/v1/commit/follow/user/' % TIKTOK_API[random.randint(0, 1)], self)
            .set_disable_default_params(True)
            .add_param('user_id', user_id)
            .add_param('sec_user_id', sec_id)
            .add_param('from', from_channel_id[0])
            .add_param('from_pre', -1)
            .add_param('type', 0)
            .add_param('channel_id', from_channel_id[1])
            .add_param('_rticket', time_stamp)
            .add_param('mcc_mnc', self.device['carrier'][0] + self.device['carrier'][1])
            .add_param('carrier_region_v2', self.device['carrier'][0])
            .add_param('op_region', 'US')
            .add_param('ts', '%s&' % int(time_stamp / 1000))
            .add_header('x-common-params-v2', True)
            .get_response('get')
        )
        if resp.status == 'fail':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def like_video_by_id(self, video_id):
        """
        """
        time_stamp = int(round(time.time() * 1000))

        resp = LikeVideoResponse(
            API('%s/aweme/v1/commit/item/digg/' % TIKTOK_API[random.randint(0, 1)], self)
            .set_disable_default_params(True)
            .add_param('aweme_id', video_id)
            .add_param('type', 1)
            .add_param('channel_id', random.randint(0, 3))
            .add_param('_rticket', time_stamp)
            .add_param('mcc_mnc', self.device['carrier'][0] + self.device['carrier'][1])
            .add_param('carrier_region_v2', self.device['carrier'][0])
            .add_param('op_region', 'US')
            .add_param('ts', '%s&' % int(time_stamp / 1000))
            .add_header('x-common-params-v2', True)
            .get_response('get')
        )
        if resp.status == 'fail':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def like_comment(self, video_id, comment_id):
        """
        """
        time_stamp = int(round(time.time() * 1000))

        resp = LikeCommentResponse(
            API('%s/aweme/v1/comment/digg/' % TIKTOK_API[random.randint(0, 1)], self)
            .set_disable_default_params(True)
            .add_param('cid', comment_id)
            .add_param('aweme_id', video_id)
            .add_param('digg_type', 1)
            .add_param('channel_id', random.randint(0, 3))
            .add_param('_rticket', time_stamp)
            .add_param('mcc_mnc', self.device['carrier'][0] + self.device['carrier'][1])
            .add_param('carrier_region_v2', self.device['carrier'][0])
            .add_param('op_region', 'US')
            .add_param('ts', '%s&' % int(time_stamp / 1000))
            .add_header('x-common-params-v2', True)
            .get_response('get')
        )
        if resp.status == 'fail':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def comment(self, text, video_id, comment_id=None, text_extra=[]):
        """
        comment on video or reply to comment
        """
        time_stamp = int(round(time.time() * 1000))

        resp = CommentResponse(
            API('%s/aweme/v1/comment/publish/' % TIKTOK_API[random.randint(0, 1)], self)
            .set_disable_default_params(True)
            .set_encoding('urlencode')
            .add_param('_rticket', time_stamp)
            .add_param('mcc_mnc', self.device['carrier'][0] + self.device['carrier'][1])
            .add_param('carrier_region_v2', self.device['carrier'][0])
            .add_param('op_region', 'US')
            .add_param('ts', '%s&' % int(time_stamp / 1000))
            .add_post('aweme_id', video_id)
            .add_post('text', text)
            .add_post('reply_id', comment_id)
            .add_post('text_extra', text_extra)
            .add_post('is_self_see', 0)
            .add_post('sticker_id', '')
            .add_post('sticker_source', 0)
            .add_post('sticker_width', 0)
            .add_post('sticker_height', 0)
            .add_post('channel_id', 3)
            .add_post('city', '')
            .add_post('action_type', 0)
            .add_header('x-common-params-v2', True)
            .get_response('post')
        )
        if resp.status == 'fail':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def share_media(self, video_id):
        time_stamp = int(round(time.time() * 1000))
        resp = ShareResponse(
            API('%s/aweme/v1/aweme/stats/' % TIKTOK_API[random.randint(0, 1)], self)
            .set_disable_default_params(True)
            .set_encoding('urlencode')
            .add_param('_rticket', time_stamp)
            .add_param('mcc_mnc', self.device['carrier'][0] + self.device['carrier'][1])
            .add_param('carrier_region_v2', self.device['carrier'][0])
            .add_param('op_region', 'US')
            .add_param('ts', '%s&' % int(time_stamp / 1000))
            .add_post('share_delta', 1)
            .add_post('stats_channel', random.choice(['copy', 'whatsapp', 'whatsapp_status', 'chat_merge', 'snapchat', 'sms']))
            .add_post('first_install_time', 1578228066)
            .add_post('action_time', int(time_stamp / 1000))
            .add_post('item_id', video_id)
            .add_post('aweme_type', 0)
            .add_header('x-common-params-v2', True)
            .get_response('post')
        )
        if resp.status == 'fail':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def view_media(self, video_id):
        time_stamp = int(round(time.time() * 1000))
        resp = ShareResponse(
            API('%s/aweme/v1/aweme/stats/' % TIKTOK_API[random.randint(0, 1)], self)
            .set_disable_default_params(True)
            .set_encoding('urlencode')
            .add_param('_rticket', time_stamp)
            .add_param('mcc_mnc', self.device['carrier'][0] + self.device['carrier'][1])
            .add_param('carrier_region_v2', self.device['carrier'][0])
            .add_param('op_region', 'US')
            .add_param('ts', '%s&' % int(time_stamp / 1000))
            .add_post('first_install_time', 1578228066)
            .add_post('action_time', int(time_stamp / 1000))
            .add_post('tab_type', 3)
            .add_post('item_id', video_id)
            .add_post('play_delta', 1)
            .add_post('aweme_type', 0)
            .add_header('x-common-params-v2', True)
            .get_response('post')
        )
        if resp.status == 'fail':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def _generate_device(self, reset_device=False):
        logger.debug('Generate device called')

        if not reset_device:
            device = to_device_dict(self.settings.get('device_string'))
            google_aid = self.settings.get('google_aid')
            openudid = self.settings.get('openudid')
            uuid = self.settings.get('uuid')
        else:
            device = google_aid = openudid = uuid= None

        # 'Google;Pixel 2 XL;2712x1440;arm64-v8a;10;29;560;QQ1A.191205.008;["312", "530", "Sprint Spectrum"]'
        device = {
            'brand': 'Google',
            'model': 'Pixel 2 XL',
            'resolution': '2712x1440',
            'cpu_abi': 'arm64-v8a',
            'os_version': '10',
            'os_api': '29',
            'dpi': '560',
            'rom_version': 'QQ1A.191205.008',
            'carrier': ["312", "530", "Sprint Spectrum"]
        }

        if not device or not google_aid or not openudid or not uuid:
            logger.debug('Generating new devices signature')
            device = random_device()
            google_aid = generate_UUID(True)
            openudid = generate_device_id()
            uuid = random_numbs(15)
            # google_aid = '9cb504b4-f7ae-4e73-ab56-186f9c6527c0'
            # openudid = '2c1c8517a2c0b748'

        data = {
            'google_aid': google_aid, 'openudid': openudid, 'uuid': uuid, **device
        }

        android = Android(data)
        while android.wait_flag:
            if time.time() - android.time > 1 * 60:
                # we have waited too long
                logger.error('device not responding')
                raise tiktok.error.AndroidDeviceError
            time.sleep(1)

        return {
            'device_string': to_device_string(device),
            'google_aid': google_aid,
            'openudid': openudid,
            'uuid': uuid,
            'device_id': android.results['device_id'],
            'install_id': android.results['install_id'],
        }
    
    def _generate_device_v2(self):
        logger.debug('Generate device_v2 called')
        self.settings.set('openudid', generate_device_id())
        self.settings.set('google_aid', generate_UUID(True))
        self.settings.set('uuid', random_numbs(15))
        self.settings.set('device_id', 0)
        self.settings.set('install_id', 0)
        self.device = random_device()
        self.settings.set('device_string', to_device_string(self.device))

        data = {
            "magic_tag":"ss_app_log","header":{"display_name":"TikTok","update_version_code":2021407050,"manifest_version_code":2021407050,"aid":1233,"channel":"googleplay","appkey":"5559e28267e58eb4c1000012","package":"com.zhiliaoapp.musically","app_version":"14.7.5","version_code":140705,"sdk_version":"2.5.5.8","os":"Android","os_version":self.device['os_version'],"os_api":self.device['os_api'],"device_model":self.device['model'],"device_brand":self.device['brand'],"cpu_abi":self.device['cpu_abi'],"release_build":"688b613_20200121","density_dpi":self.device['dpi'],"display_density":"mdpi","resolution":self.device['resolution'],"language":"en","mc":self.device['mc'],"timezone":0,"access":"wifi","not_request_sender":0,"rom":self.device['rom_version'],"rom_version":self.device['rom_version'],"sig_hash":"194326e82c84a639a52e5c023116f12a","google_aid":self.settings.get('google_aid'),"device_id":self.settings.get('device_id'),"openudid":self.settings.get('openudid'),"install_id":self.settings.get('install_id'),"clientudid":generate_UUID(True),"sim_serial_number":[],"region":"US","tz_name":"America/New_York","tz_offset":0,"sim_region":"us"},"_gen_time":int(round(time.time() * 1000))}
        req = (
            API('https://log2.musical.ly/service/2/device_register/', self)
            .add_posts(data)
            .set_repeat_params(True)
        )
        req._add_default_params()
        url = req._full_url(req.url, req.params)
        ts = int(time.time())
        x_gorgon = req._get_xgorgon(ts, req._query_string(url))

        headers = {
            'sdk-version': '1',
            'Content-Type': 'application/json; charset=utf-8',
            'User-Agent': 'okhttp/3.10.0.1',
            'Cookie': 'sessionid=',
            'X-SS-STUB': message_digest(req.get_body()).upper(),
            'X-Gorgon': x_gorgon,
            'X-Khronos': str(ts),
        }

        error_counter = 0
        while True:
            try:
                resp = requests.post(url, proxies=req._proxy, headers=headers, data=req.get_body(), timeout=60, verify=True)
                break
            except (requests.exceptions.RequestException, requests.exceptions.ProxyError) as e:
                logger.error('Proxy/ConnectionError error (%s): %s' %(error_counter, e))
                error_counter += 1
                if error_counter > 3:
                    raise
                time.sleep(max(error_counter, 1) * 5)

        if resp.status_code != 200:
            resp.raise_for_status()
            # raise Exception('Connection error!!')
        resp = resp.json()
        # print('device_register', resp)

        self.settings.set('device_id', resp['device_id'])
        self.settings.set('install_id', resp['install_id'])
        self.settings.set_cookie('install_id', resp['install_id'])

        self.v_1()
        time.sleep(3)
        data = self.v_2()
        time.sleep(3)
        self.v_3(data)

    def v_1(self):
        req = (
            API('https://xlog-va.musical.ly/v2/s/', self)
            .set_disable_default_params(True)
            .add_param('os', 0)
            .add_param('ver', '0.6.10.25.17-IH-Ov')
            .add_param('m', 1)
            .add_param('app_ver', '14.7.5')
            .add_param('region', 'en_')
            .add_param('aid', '1233')
            .add_param('did', self.settings.get('device_id'))
        )
        url = req._full_url(req.url, req.params)
        ts = int(time.time())
        x_gorgon = req._get_xgorgon(ts, req._query_string(url))

        headers = {
            'sdk-version': '1',
            'User-Agent': 'okhttp/3.10.0.1',
            'Cookie': 'sessionid=',
            'X-Gorgon': x_gorgon,
            'X-Khronos': str(ts),
        }

        error_counter = 0
        while True:
            try:
                resp = requests.get(url, proxies=req._proxy, headers=headers, timeout=60, verify=True)
                break
            except (requests.exceptions.RequestException, requests.exceptions.ProxyError) as e:
                logger.error('Proxy/ConnectionError error (%s): %s' %(error_counter, e))
                error_counter += 1
                if error_counter > 3:
                    raise
                time.sleep(max(error_counter, 1) * 5)

        if resp.status_code != 200:
            resp.raise_for_status()
            # raise Exception('Connection error!!')
        # resp = resp.json()
        # print('v_1', resp.text)

    def v_2(self):
        req = (
            API('https://sdfp-va.musical.ly/v1/getInfo', self)
            .set_disable_default_params(True)
            .add_param('app_id', 1233)
            .add_param('version_code', 4)
            .add_param('time', 1596894860525)
            .add_param('os', 'android')
            .add_param('did', self.settings.get('device_id'))
            .add_param('version', '1.0.3')
        )
        data = 'ApYWeowee4l/0k1Pk1cv0bNi+GxeEcOer7N8R5w0SI1HielM60oNdUe7omtVAvEUHI4z9d/MPVUm3yw7HHoBfqqOa0fzUP5jHhmf+nwvb+RpGyXjgePhoKNmFcJ7JKla/I4zdGY72WyKn4qaUUiz4wZPF8pY3n4iULFSFVnKYQLj+CULSxkzyy4kD+9Ip4ho7qM9D40dlbVW+Lagq8CFjrCPSzuB9iOJD0qhKpbs2jSlvYrxoXWmifdiPmm7qxVLPtDJdp3VOKM4OJxYvjTAyIb4gtbYOPqLSuXOYbhSF7zHjHbMXNlwITUloEHcYtMUbc563eLTujOsS+iOHzNOIrpOdMXthtKQbySeWp6crparoezAqhEWA+YJEBidb++u3OWQ1IuPmhPLsK+tW+oDx0dA1qQCsTLAEaZfBPleTSp4sQkIn2f86VCDVubTqbWvLzVGCFn7Zar+4Sim8LLFQPYxWtwjIMzuAKeGYpUDFUgtMGeOBufuixgTf6AgwNdxLx8GaJPPo4aPxTzJtUIqm0YDl5H9N2MX/UxtufdP0lXaReEvQClBlM/Qb0wRxlj894KfVF6/pcENU2ThdYek/h7QgQMoXJ/zjTiuA790hd3HW9mY4v0aJD4Sc3sEyiOJZJ5upfamLR/L1bF/IVL01vdLHjBHvENts1dIvMwbfrTuAMDq6QUa7bM9wJj1yQGOCPAv18mV26WOJWkikGKg1+veD2zG4zC+pjMXrfXDM27pmjvujdEIC1nZuYGU3ogWok7vi83LE31wxe13X7s1r3G87qT4T7hYn7keM+78UrPRO+oI6OrLMKle/Qj/b86/1sYJx+DOQ8hhKEF8zVn1TP0QAVqSPKlkp0wg8UrBgpSdYW1OhEcqzq8U2JG3ij8UesV2PuMItdmMYI3+xCF6Zd6h9q1bogWkPRCcS+G5oJBKJEUyTt977k7znrFi9duiW2TBZkOFPdwv4fqxL21T9aYFl/CVAIQGhmD0P30='

        url = req._full_url(req.url, req.params)
        ts = int(time.time())
        x_gorgon = req._get_xgorgon(ts, req._query_string(url))
        headers = {
            'sdk-version': '1',
            'Content-Type': 'application/octet-stream',
            'User-Agent': 'okhttp/3.10.0.1',
            'Cookie': 'sessionid=',
            'X-Gorgon': x_gorgon,
            'X-Khronos': str(ts),
        }
        error_counter = 0
        while True:
            try:
                resp = requests.post(url, proxies=req._proxy, headers=headers, data=base64.b64decode(data), timeout=60, verify=True)
                break
            except (requests.exceptions.RequestException, requests.exceptions.ProxyError) as e:
                logger.error('Proxy/ConnectionError error (%s): %s' %(error_counter, e))
                error_counter += 1
                if error_counter > 3:
                    raise
                time.sleep(max(error_counter, 1) * 5)

        if resp.status_code != 200:
            # raise Exception('Connection error!!')
            return {}
        # resp = resp.json()
        # print('v_2', resp.text)
        return resp.json()

    def v_3(self, data):
        grilock = base64.b64encode(
            json.dumps({"os":"Android","version":"1.0.3","token_id": data.get("token_id", 0),"code":200}).encode()
        ).decode('ascii')
        postData = '{"extra":"SS-200","grilock":"'+grilock+'=","p1":"'+str(self.settings.get('device_id'))+'","p2":"'+str(self.settings.get('install_id'))+'","ait":1597968567,"uit":113,"pkg":"com.zhiliaoapp.musically","prn":"CZL-MRT","vc":2021305030,"fp":"'+self.device['brand']+'/'+self.device['brand']+'/'+self.device['model']+':'+self.device['os_version']+'/20171130.376229:user/release-keys","mdi_if":{},"mdi_s":0,"wifisid":"kopgnsu'+str(random.randint(0,99999))+'","wifimac":"'+self.device['mc']+'","wifip":"192.168.0.20","vpn":0,"aplist":[],"route":{"iip":"192.168.0.20","gip":"192.168.0.1","ghw":"'+self.device['mc']+'","type":"wlan0"},"location":"","hw":{"brand":"'+self.device['brand']+'","model":"'+self.device['model']+'","board":"'+self.device['brand']+'","device":"'+self.device['model']+'","product":"'+self.device['model']+'","manuf":"'+self.device['brand']+'","bt":"uboot","pfbd":"gmin","display":"'+'*'.join(self.device['resolution'].split('x'))+'","dpi":'+str(self.device['dpi'])+',"bat":1000,"cpu":{"core":4,"hw":"placeholder","max":"2400000","min":"1000000","ft":"swp half thumb fastmult vfp edsp neon vfpv3 tls vfpv4 idiva idivt"},"mem":{"ram":"3718152192","rom":"8320901120","sd":"8320901120"}},"id":{"i":25,"r":"7.1.2","imei":"","imsi":"","adid":"'+self.settings.get('openudid')+'","adid_ex":"'+self.settings.get('openudid')+'","mac":"'+self.device['mc']+'","serial":"55577289"},"emulator":{"sig":0,"cb":1,"cid":16778240,"br":"Intel(R) Core(TM) i7-7700 CPU @ 3.60GHz","file":[],"prop":[],"ghw":0},"env":{"ver":"0.6.08.27.04","tag":"NewVersion2","pkg":"com.zhiliaoapp.musically","tz":"GMT+03:00","ml":"tr_TR","uid":10072,"mc":0,"arch":1,"e_arch":3,"v_bnd":7,"su":1,"sp":"/system/bin/su","ro.secure_s":"1","ro.debuggable_s":"0","rebuild":0,"jd":0,"dbg":0,"tid":0,"trm":"","hph":"192.168.0.10","hpp":"7754","envrion":[],"xposed":0,"frida":0,"cydia":0,"jexp":0,"click":"","acb":0,"hook":[],"jvh":[],"fish":{},"vapp":"","vmos":0},"extension":{"notify":2212858197,"sg_s":1,"sign":"194326E82C84A639A52E5C023116F12A","sha1":"D79F7CB8509A5E7E71C4F2AFCFB75EA8C87177CA","inst":"android.app.Instrumentation","AMN":"android.app.ActivityManagerProxy","dump":1,"dump2":1,"mk":0,"cba":"0x0e073420","prns":"tp-io-6,NetNormal#1,NetNormal#2,NetNormal#3,NetNormal#4,NetNormal#5,NetNormal#6,NetNormal#7","bytes64":"","plt":""},"paradox":{"add":0,"cba":0,"bsy":0,"p_uit_1":0,"p_uit_2":0,"f_uit":0,"f_prn":0},"gp_ctl":{"usb":-1,"adb":-1,"acc":"-8,7, -0,2, 4,4"},"custom_info":{},"fch":"0993919008"}'

        req = (
            API('https://xlog-va.musical.ly/v2/r', self)
            .set_disable_default_params(True)
            .add_param('os', 0)
            .add_param('ver', '0.6.10.25.17-IH-Ov')
            .add_param('m', 2)
            .add_param('app_ver', '14.7.5')
            .add_param('region', 'en_')
            .add_param('aid', '1233')
            .add_param('did', self.settings.get('device_id'))
            .add_param('iid', self.settings.get('install_id'))
        )

        url = req._full_url(req.url, req.params)
        ts = int(time.time())
        x_gorgon = req._get_xgorgon(ts, req._query_string(url))
        headers = {
            'sdk-version': '1',
            'Content-Type': 'application/json; charset=utf-8',
            'User-Agent': 'okhttp/3.10.0.1',
            'X-SS-STUB': message_digest(postData).upper(),
            'Cookie': 'sessionid=',
            'X-Gorgon': x_gorgon,
            'X-Khronos': str(ts),
        }
        error_counter = 0
        while True:
            try:
                resp = requests.post(url, proxies=req._proxy, headers=headers, data=postData, timeout=60, verify=True)
                break
            except (requests.exceptions.RequestException, requests.exceptions.ProxyError) as e:
                logger.error('Proxy/ConnectionError error (%s): %s' %(error_counter, e))
                error_counter += 1
                if error_counter > 3:
                    raise
                time.sleep(max(error_counter, 1) * 5)

        if resp.status_code != 200:
            resp.raise_for_status()
            # raise Exception('Connection error!!')
        # resp = resp.json()
        print('v_3', resp.text)
        return resp

    def _device_sdk_stats_collect(self, i):
        """ 
        """
        if i == 1:
            data = {
                "type":"header","data":{"manifest_version_code":0,"app_language":int(random_numbs(3)),"access":0,"app_version":0,"device_model":0,"timezone":0,"channel":0,"language":0,"header_all":int(random_numbs(3)),"resolution":int(random_numbs(1)),"update_version_code":0,"rom":int(random_numbs(1)),"app_region":int(random_numbs(3)),"os_api":0,"cpu_abi":0,"install_id":0,"new_user_mode":0,"tz_name":0,"tz_offset":0,"mc":0,"udid":0,"package":0,"device_id":0,"aliyun_uuid":0,"mcc_mnc":int(random_numbs(1)),"os_version":0,"version_code":0,"serial_number":0,"display_name":int(random_numbs(1)),"display_density":int(random_numbs(1)),"clientudid":int(random_numbs(1)),"carrier":int(random_numbs(1)),"google_aid":int(random_numbs(3)),"app_track":0,"sim_serial_number":0,"sig_hash":0,"appkey":0,"sim_region":int(random_numbs(1)),"region":0,"rom_version":int(random_numbs(1))}
            }
        elif i == 2:
            api_url = API('https://log2.musical.ly/service/2/device_register/', self)
            api_url._add_default_params()
            data = {
                "type":"device_register",
                "data":{
                    "timestampPrimaryId":1,
                    "init_start":42799358,
                    "init_end":42800033,
                    "prepare_param_start":42800034,
                    "prepare_param_end":42800034,
                    "load_cache_start":42799366,
                    "load_cache_end":42799386,
                    "max_try_times":2,
                    "calls":[
                        {
                            "net_request_start":42800042,
                            "net_request_end":42805694,
                            "url":api_url._full_url(api_url.url, api_url.params),
                            "data":json.dumps(
                                {"magic_tag":"ss_app_log","header":{"display_name":"TikTok","update_version_code":2021407050,"manifest_version_code":2021407050,"aid":1233,"channel":"googleplay","appkey":"5559e28267e58eb4c1000012","package":"com.zhiliaoapp.musically","app_version":"14.7.5","version_code":140705,"sdk_version":"2.5.5.8","os":"Android","os_version":self.device['os_version'],"os_api":self.device['os_api'],"device_model":self.device['model'],"device_brand":self.device['brand'],"cpu_abi":self.device['cpu_abi'],"release_build":"688b613_20200121","density_dpi":self.device['dpi'],"display_density":"mdpi","resolution":self.device['resolution'],"language":"en","mc":self.device['mc'],"timezone":0,"access":"wifi","not_request_sender":0,"rom":self.device['rom_version'],"rom_version":self.device['rom_version'],"sig_hash":"194326e82c84a639a52e5c023116f12a","google_aid":self.settings.get('google_aid'),"device_id":self.settings.get('device_id'),"openudid":self.settings.get('openudid'),"install_id":self.settings.get('install_id'),"clientudid":generate_UUID(True),"sim_serial_number":[],"region":"US","tz_name":"America/New_York","tz_offset":0,"sim_region":"us"},"_gen_time":int(round(time.time() * 1000))}),
                            "exception":"",
                            "n_try":0
                        }
                    ],
                    "current_did":self.settings.get('device_id')
                }
            }
        else:
            api_url = API('https://log2.musical.ly/service/2/app_alert_check/', self)
            api_url.add_param('google_aid', self.settings.get('google_aid'))
            api_url._add_default_params()
            data = {
                "type":"active_user",
                "data":{
                    "timestamp_active_user_id":1,
                    "active_user_invoke_internal_start":42812652,
                    "active_user_invoke_internal_end":42812652,
                    "internal_json_object":{
                        "sHasLoadDid":True,
                        "sPendingActiveUser":True,
                        "networkNotAvailable":True,
                        "now":int(round(time.time() * 1000)),
                        "sFetchActiveTime":0,
                        "durationSinceLastLaunchActiveThread":int(round(time.time() * 1000)),
                        "launchActiveThreadTooFrequently":False
                    },
                    "active_thread_run":42812653,
                    "active_user_start":42812653,
                    "active_user_end":42822438,
                    "active_user_net_start":42812661,
                    "active_user_net_stacktrace":"",
                    "net_url":api_url._full_url(api_url.url, api_url.params)
                }
            }

        resp = Response(
            API('https://log2.musical.ly/service/2/device_sdk/stats_collect/', self)
            .add_posts(data)
            .set_repeat_params(True)
            .get_response('post')
        )
        # if resp.status != 'ok':
        #     tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def _user_info(self):
        """
        """
        resp = Response(
            API('%s/2/user/info/' % TIKTOK_API[random.randint(0, 1)], self)
            .get_response('get')
        )
        try:
            old_token = self.settings.get('X-Tt-Token')
            self.settings.set('X-Tt-Token', resp.headers['X-Tt-Token'])
            self.settings.set('X-Tt-Token-Sign', resp.headers['X-Tt-Token-Sign'])
            logger.info('X-Tt-Token changed from %s to %s' %(old_token, self.settings.get('X-Tt-Token')))
        except KeyError:
            pass

        
        # if resp.status != 'ok':
        #     tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def _check_in(self):
        """
        """
        time_stamp = int(round(time.time() * 1000))
        resp = CheckInResponse(
            API('%s/aweme/v1/check/in/' % TIKTOK_API[random.randint(0, 1)], self)
            .set_disable_default_params(True)
            .add_param('_rticket', time_stamp)
            .add_param('carrier_region_v2', self.device['carrier'][0])
            .add_param('op_region', 'US')
            .add_param('ts', '%s&' % int(time_stamp / 1000))
            .add_header('x-common-params-v2', True)
            .get_response('get')
        )
        if resp.status != 'ok':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def _im_reboot_misc(self):
        """
        """
        time_stamp = int(round(time.time() * 1000))
        resp = Response(
            API('%s/aweme/v1/im/reboot/misc/' % TIKTOK_API[random.randint(0, 1)], self)
            .set_disable_default_params(True)
            .add_param('r_cell_status', 0)
            .add_param('is_active_x', 0)
            .add_param('im_token', 1)
            .add_param('_rticket', time_stamp)
            .add_param('carrier_region_v2', self.device['carrier'][0])
            .add_param('op_region', 'US')
            .add_param('ts', '%s&' % int(time_stamp / 1000))
            .add_header('x-common-params-v2', True)
            .get_response('get')
        )
        # if resp.status != 'ok':
        #     tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def get_self_info(self, is_after_login=0):
        resp = UserResponse(
            API('%s/aweme/v1/user/profile/self/' %
                TIKTOK_API[random.randint(0, 1)], self)
            .add_param('is_after_login', is_after_login)
            .set_disable_default_params(True)
            ._add_default_params()
            .add_param('manifest_version_code', 2021607020)
            .add_param('ab_version', '16.7.2')
            .add_param('version_name', '16.7.2')
            .add_param('build_number', '16.7.2')
            .add_param('version_code', 160702)
            .get_response('get')
        )
        if resp.status != 'ok':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def _device_register(self):
        """ 
        """
        if not self.device.get('mc'):
            self.device['mc'] = rand_mac()
            self.settings.set('device_string', to_device_string(self.device))

        data = {"magic_tag":"ss_app_log","header":{"display_name":"TikTok","update_version_code":2021407050,"manifest_version_code":2021407050,"aid":1233,"channel":"googleplay","appkey":"5559e28267e58eb4c1000012","package":"com.zhiliaoapp.musically","app_version":"14.7.5","version_code":140705,"sdk_version":"2.5.5.8","os":"Android","os_version":self.device['os_version'],"os_api":self.device['os_api'],"device_model":self.device['model'],"device_brand":self.device['brand'],"cpu_abi":self.device['cpu_abi'],"release_build":"688b613_20200121","density_dpi":self.device['dpi'],"display_density":"mdpi","resolution":self.device['resolution'],"language":"en","mc":self.device['mc'],"timezone":0,"access":"wifi","not_request_sender":0,"rom":self.device['rom_version'],"rom_version":self.device['rom_version'],"sig_hash":"194326e82c84a639a52e5c023116f12a","google_aid":self.settings.get('google_aid'),"device_id":self.settings.get('device_id'),"openudid":self.settings.get('openudid'),"install_id":self.settings.get('install_id'),"clientudid":generate_UUID(True),"sim_serial_number":[],"region":"US","tz_name":"America/New_York","tz_offset":0,"sim_region":"us"},"_gen_time":int(round(time.time() * 1000))}

        resp = Response(
            API('https://log2.musical.ly/service/2/device_register/', self)
            .add_posts(data)
            .set_repeat_params(True)
            .get_response('post')
        )
        # if resp.status != 'ok':
        #     tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def _log_settings(self):
        """ 
        """
        time_stamp = int(round(time.time() * 1000))
        finger_print = {"sim_op":"62002","phone_type":1,"net_type":0,"wifi_bssid":self.device['mc']}

        data = {"magic_tag":"ss_app_log","header":{"appkey":"5559e28267e58eb4c1000012","openudid":self.settings.get('openudid'),"sdk_version":"2.5.5.8","package":"com.zhiliaoapp.musically","channel":"googleplay","display_name":"TikTok","app_version":"14.7.5","version_code":2021407050,"timezone":0,"access":"wifi","os":"Android","os_version":self.device['os_version'],"os_api":self.device['os_api'],"device_model":self.device['model'],"device_brand":self.device['brand'],"language":"en","resolution":self.device['resolution'],"display_density":"mdpi","density_dpi":self.device['dpi'],"mc":self.device['mc'],"clientudid":generate_UUID(True),"install_id":self.settings.get('install_id'),"device_id":self.settings.get('device_id'),"sig_hash":"194326e82c84a639a52e5c023116f12a","aid":1233,"push_sdk":[1,2,6,7,8,9],"rom":self.device['rom_version'],"release_build":"688b613_20200121","update_version_code":2021407050,"manifest_version_code":2021407050,"cpu_abi":"arm64-v8a","sim_serial_number":[],"not_request_sender":0,"rom_version":self.device['rom_version'],"region":"US","tz_name":"America/New_York","tz_offset":0,"sim_region":"gh","google_aid":self.settings.get('google_aid')},"_gen_time":time_stamp,"fingerprint":pack_string(json.dumps(finger_print))}

        resp = Response(
            API('https://log2.musical.ly/service/2/log_settings/', self)
            .add_posts(data)
            .set_repeat_params(True)
            .get_response('post')
        )
        # if resp.status != 'ok':
        #     tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def _app_log(self):
        """ 
        """
        session_1 = generate_UUID(True)
        session_2 = generate_UUID(True)

        data = {
            "event":[
                {
                    "nt":4,
                    "tea_event_index":0,
                    "local_time_ms":int(round(time.time() * 1000)),
                    "category":"umeng",
                    "tag":"monitor",
                    "label":"terminate",
                    "user_id":self.settings.get('user_id'),
                    "session_id":session_1,
                    "datetime":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "event_id":389
                },
                {
                    "nt":4,
                    "tea_event_index":1,
                    "local_time_ms":int(round(time.time() * 1000)),
                    "category":"umeng",
                    "tag":"monitor",
                    "label":"launch",
                    "user_id":self.settings.get('user_id'),
                    "session_id":session_1,
                    "datetime":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "event_id":390
                }
            ],
            "event_v3":[
                {
                    "nt":4,
                    "user_id":self.settings.get('user_id'),
                    "ab_sdk_version":"1320912",
                    "event":"request_anchor_list",
                    "params":{
                        "tea_event_index":1,
                        "local_time_ms":int(round(time.time() * 1000))
                    },
                    "event_id":391,
                    "session_id":session_2,
                    "datetime":datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                },
                {
                    "nt":4,
                    "user_id":self.settings.get('user_id'),
                    "ab_sdk_version":"1320912",
                    "event":"anchor_list_success",
                    "params":{
                        "anchor_type":"[]",
                        "tea_event_index":2,
                        "local_time_ms":int(round(time.time() * 1000))
                    },
                    "event_id":392,
                    "session_id":session_2,
                    "datetime":datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            ],
            "launch":[
                {
                    "datetime":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "session_id":generate_UUID(True),
                    "local_time_ms":int(round(time.time() * 1000)),
                    "tea_event_index":0,
                    "is_background":True,
                    "ab_sdk_version":"1320912"
                },
                {
                    "datetime":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "session_id":generate_UUID(True),
                    "local_time_ms":int(round(time.time() * 1000)),
                    "tea_event_index":0,
                    "ab_sdk_version":"1320912"
                }
            ],
            "magic_tag":"ss_app_log",
            "time_sync":{
                "server_time":int(round(time.time() * 1000)),
                "local_time":int(round(time.time() * 1000))
            },
            "header":{
                "appkey":"5559e28267e58eb4c1000012",
                "openudid":self.settings.get('openudid'),
                "sdk_version":"2.5.5.8",
                "package":"com.zhiliaoapp.musically",
                "channel":"googleplay",
                "display_name":"TikTok",
                "app_version":"14.7.5",
                "version_code":2021407050,
                "timezone":0,
                "access":"wifi",
                "os":"Android",
                "os_version":self.device['os_version'],
                "os_api":self.device['os_api'],
                "device_model":self.device['model'],
                "device_brand":self.device['brand'],
                "language":"en",
                "resolution":self.device['resolution'],
                "display_density":"mdpi",
                "density_dpi":self.device['dpi'],
                "mc":self.device['mc'],
                "clientudid":generate_UUID(True),
                "install_id":self.settings.get('install_id'),
                "device_id":self.settings.get('device_id'),
                "sig_hash":"194326e82c84a639a52e5c023116f12a",
                "aid":1233,
                "push_sdk":[
                    1,
                    2,
                    6,
                    7,
                    8,
                    9
                ],
                "rom":self.device['rom_version'],
                "release_build":"688b613_20200121",
                "update_version_code":2021407050,
                "manifest_version_code":2021407050,
                "cpu_abi":self.device['cpu_abi'],
                "sim_serial_number":[],
                "not_request_sender":0,
                "rom_version":self.device['rom_version'],
                "region":"US",
                "tz_name":"America/New_York",
                "tz_offset":0,
                "sim_region":"us",
                "google_aid":self.settings.get('google_aid'),
                "app_language":"en",
                "sys_region":"US",
                "carrier_region":"US",
                "timezone_name":"Greenwich Mean Time",
                "timezone_offset":"0"
            },
            "_gen_time":int(round(time.time() * 1000))
        }

        resp = Response(
            API('https://log2.musical.ly/service/2/app_log/', self)
            .add_posts(data)
            .set_repeat_params(True)
            .get_response('post')
        )
        # if resp.status != 'ok':
        #     tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def _app_alert_check(self):
        resp = Response(
            API('https://log2.musical.ly/service/2/app_alert_check/', self)
            .add_param('google_aid', self.settings.get('google_aid'))
            .set_repeat_params(True)
            .get_response('get')
        )
        # if resp.status != 'ok':
        #     tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def _set_user(self, username, pwd=None, reset_device=False, proxy=None):
        logger.debug('Setting user %s' % username)
        self.settings.set_user(username)
        if proxy != None:
            self.proxy = proxy

        if not self.settings.get('device_id') or not self.settings.get('install_id') or reset_device:
            # device_info = self._generate_device(reset_device)
            # self.settings.set('username', username)
            # self.settings.set('google_aid', device_info['google_aid'])
            # self.settings.set('openudid', device_info['openudid'])
            # self.settings.set('device_id', device_info['device_id'])
            # self.settings.set('install_id', device_info['install_id'])
            # self.settings.set('device_string', device_info['device_string'])
            # self.settings.set_cookie('sec_sessionid', '')
            # self.settings.set_cookie('install_id', device_info['install_id'])
            try:
                self._generate_device_v2()
            except Exception:
                logger.exception('%s: Generating new device failed' %(username))
                raise
            else:
                self.login_flow = True
                
            logger.debug('SetUser done.')

        # if (not self.settings.get('X-Tt-Token') or not self.settings.get('session_key')) and not 'sessionid' in self.settings.get_cookies():
        #     self.is_logged_in = False
        if not self.settings.get('X-Tt-Token') or not self.settings.get('session_key'):
            self.is_logged_in = False
        else:
            self.is_logged_in = True

        self.username = username
        self.pwd = pwd
        device_str = self.settings.get('device_string')
        if not device_str:
            device_str = 'Google;Pixel 2 XL;2712x1440;armeabi-v7a;10;25;560;QQ1A.191205.008;["312", "530", "Sprint Spectrum"]'
            self.settings.set('device_string', device_str)
        self.device = to_device_dict(device_str)
        logger.info('is_logged_in: %s' % self.is_logged_in)

    def _update_login_state(self, response):
        """
        :response: LoginResponse
        """
        logger.info('update_login_state..')
        self.settings.set('X-Tt-Token', response.headers['X-Tt-Token'])
        self.settings.set('X-Tt-Token-Sign',
                          response.headers['X-Tt-Token-Sign'])
        self.settings.set('X-Tt-Multi-Sids',
                          response.headers['X-Tt-Multi-Sids'])
        self.settings.set('user_id', response.user_id)
        self.settings.set('username', response.username)
        # self.settings.set('pwd', self.pwd)
        self.settings.set('session_key', response.session_key)
        self.settings.set('sec_user_id', response.sec_user_id)

        self.is_logged_in = True

    def _send_login_flow(self, just_logged_in):
        logger.info('send_login_flow..')
        if just_logged_in:
            resp = self.get_self_info(1)
            self.settings.set('username', resp.user.username)
            return resp
        else:
            # TODO
            # we're resuming already looged in session
            # we might wanna check if our session is still valid
            # sometimes upon opening the app new id is generated
            self._user_info()
            self._device_sdk_stats_collect(1)
            self._check_in()
            resp = self.get_self_info()
            self._im_reboot_misc()
            self._device_register()
            self._log_settings()
            self._app_log()
            self._device_sdk_stats_collect(2)
            self._app_alert_check()
            self._device_sdk_stats_collect(3)
            return resp

    def get_user_info(self, sec_id=None, username=None):
        if not sec_id and not username:
            raise TypeError('Provide user sec_user_id or username')

        if not sec_id:
            _, sec_id = username_to_id(username)
        resp = UserResponse(
            API('%s/aweme/v1/user/profile/other/' %
                TIKTOK_API[random.randint(0, 1)], self)
            .add_param('sec_user_id', sec_id)
            .get_response('get')
        )
        if resp.status != 'ok':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def get_user_info_v2(self, user_id, sec_id):
        resp = UserResponse(
            API('%s/aweme/v1/user/' %
                TIKTOK_API[random.randint(0, 1)], self)
            .add_param('user_id', user_id)
            .add_param('sec_user_id', sec_id)
            .get_response('get')
        )
        if resp.status != 'ok':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def get_user_videos(self, sec_user_id, max_cursor=0, count=20):
        resp = UserVideoListResponse(
            API('%s/aweme/v1/aweme/post/' % TIKTOK_API[random.randint(0, 1)], self)
            .add_param('sec_user_id', sec_user_id)
            .add_param('source', 0)
            .add_param('max_cursor', max_cursor)
            .add_param('count', count)
            .get_response('get')
        )
        if resp.status != 'ok':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp
    
    def get_self_videos(self):
        return self.get_user_videos(self.settings.get('sec_user_id'))

    def get_followers(self, user_id, sec_user_id, max_time=0, offset=0, count=20, source_type=2):
        """
        description here
        """
        time_stamp = int(round(time.time() * 1000))
        resp = FollowersFollowingsResponse(
            API('%s/aweme/v1/user/follower/list/' %
                TIKTOK_API[random.randint(0, 1)], self)
            .set_disable_default_params(True)
            .add_param('user_id', user_id)
            .add_param('sec_user_id', sec_user_id)
            .add_param('max_time', max_time)
            .add_param('count', count)
            .add_param('offset', offset)
            .add_param('source_type', source_type)
            .add_param('address_book_access', 2)
            .add_param('gps_access', 2)
            .add_param('_rticket', time_stamp)
            .add_param('mcc_mnc', self.device['carrier'][0] + self.device['carrier'][1])
            .add_param('carrier_region_v2', self.device['carrier'][0])
            .add_param('op_region', 'US')
            .add_param('ts', '%s&' % int(time_stamp / 1000))
            .add_header('x-common-params-v2', True)
            .get_response('get')
        )
        if resp.status != 'ok':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def get_followings(self, user_id, sec_user_id, max_time=0, offset=0, count=20):
        """
        description here
        """
        time_stamp = int(round(time.time() * 1000))
        resp = FollowersFollowingsResponse(
            API('%s/aweme/v1/user/following/list/' %
                TIKTOK_API[random.randint(0, 1)], self)
            .set_disable_default_params(True)
            .add_param('user_id', user_id)
            .add_param('sec_user_id', sec_user_id)
            .add_param('max_time', max_time)
            .add_param('count', count)
            .add_param('offset', offset)
            .add_param('source_type', 2)
            .add_param('address_book_access', 2)
            .add_param('gps_access', 2)
            .add_param('_rticket', time_stamp)
            .add_param('mcc_mnc', self.device['carrier'][0] + self.device['carrier'][1])
            .add_param('carrier_region_v2', self.device['carrier'][0])
            .add_param('op_region', 'US')
            .add_param('ts', '%s&' % int(time_stamp / 1000))
            .add_header('x-common-params-v2', True)
            .get_response('get')
        )
        if resp.status != 'ok':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def get_self_followers(self, max_time=0, offset=0):
        """
        description here
        """
        return self.get_followers(self.settings.get('user_id'), self.settings.get('sec_user_id'), max_time, offset)

    def get_self_followings(self, max_time=0, offset=0):
        """
        description here
        """
        return self.get_followings(self.settings.get('user_id'), self.settings.get('sec_user_id'), max_time, offset)

    def check_email(self, email):
        response = CheckEmailResponse(
            API('%s/passport/user/check_email_registered' %
                TIKTOK_API[0], self)
            .set_encoding('urlencode')
            .add_param('account_sdk_version', '380')
            .add_post('account_sdk_source', 'app')
            .add_post('mix_mode', 1)
            .add_post('multi_login', 1)
            .add_post('email', xorEncrypt(email))
            .get_response('post')
        )
        if response.status != 'ok':
            tiktok.error.throw_exception(
                response.error_code, response.error_message)
        return response

    def create_account_by_email(self, email, pwd, proxy=None, temp_username=None):
        if not temp_username:
            temp_username = self._temp_username()
            
        # generate new install_id and device_id
        self._set_user(temp_username, pwd, proxy=proxy)
        self.settings.set('email', email)
        self.settings.set('pwd', pwd)


        # print('temp: ', temp_username)

        sleep_time = random.randint(10, 20)
        print('create_account_by_email sleeping for {}'.format(sleep_time))
        time.sleep(sleep_time)
        
        email = email.split(':')[0].strip()
        response = LoginResponse(
            API('%s/passport/email/register/v2/' % TIKTOK_API[0], self)
            .set_encoding('urlencode')
            .add_param('account_sdk_version', '380')
            .add_post('password', xorEncrypt(pwd))
            .add_post('account_sdk_source', 'app')
            .add_post('mix_mode', 1)
            .add_post('multi_login', 1)
            .add_post('email', xorEncrypt(email))
            .get_response('post')
        )
        if response.status != 'ok':
            if response.error_code == 2013:
                # succes, we can go ahead and call send_email_code
                return response

            # else, i don't know what. go ahead and throw an exception
            tiktok.error.throw_exception(
                response.error_code, response.error_message)

        
        # we shouldn't reach here
        self._update_login_state(response)
        # update temp username
        self.settings.rename(self.username, response.username)
        self._set_user(response.username, pwd)
        return self._send_login_flow(just_logged_in=True)

    def send_email_code(self, email=None, pwd=None):
        if not email:
            email = self.settings.get('email')
            email = email.split(':')[0].strip()
        
        if not pwd:
            pwd = self.settings.get('pwd')
        
        response = SendEmailCodeResponse(
            API('%s/passport/email/send_code/' % TIKTOK_API[0], self)
            .set_encoding('urlencode')
            .add_param('account_sdk_version', '380')
            .add_post('password', xorEncrypt(pwd))
            .add_post('account_sdk_source', 'app')
            .add_post('mix_mode', 1)
            .add_post('multi_login', 1)
            .add_post('type', 34)
            .add_post('email', xorEncrypt(email))
            .get_response('post')
        )
        if response.status != 'ok':
            tiktok.error.throw_exception(
                response.error_code, response.error_message)
        return response
        
    def verify_email_code(self, code, email=None):
        if not email:
            email = self.settings.get('email')
            email = email.split(':')[0].strip()
        response = LoginResponse(
            API('%s/passport/email/register_verify_login/' % TIKTOK_API[0], self)
            .set_encoding('urlencode')
            .add_param('account_sdk_version', '380')
            .add_post('code', code)
            .add_post('account_sdk_source', 'app')
            .add_post('mix_mode', 1)
            .add_post('multi_login', 1)
            .add_post('type', 34)
            .add_post('email', xorEncrypt(email))
            .get_response('post')
        )
        if response.status != 'ok':
            tiktok.error.throw_exception(
                response.error_code, response.error_message)
        
        # return response
        self._update_login_state(response)
        # update temp username
        self.settings.rename(self.username, response.username)
        self._set_user(response.username)
        return self._send_login_flow(just_logged_in=True)

    def create_account_by_phone(self, phone_number, temp_username=None, proxy=None):
        if not temp_username:
            temp_username = self._temp_username()
        # generate new install_id and device_id
        self._set_user(temp_username)
        self.settings.set('phone', phone_number)
        self.proxy = proxy

        response = SendSmsCodeResponse(
            API('%s/passport/mobile/send_code/v1/' %
                TIKTOK_API[random.randint(0, 1)], self)
            .set_encoding('urlencode')
            .add_param('account_sdk_version', '380')
            .add_post('check_register', 0)
            .add_post('auto_read', 1)
            .add_post('account_sdk_source', 'app')
            .add_post('unbind_exist', '35')
            .add_post('mix_mode', 1)
            .add_post('mobile', xorEncrypt(phone_number))
            .add_post('multi_login', 1)
            .add_post('type', 3731)
            .get_response('post')
        )
        if response.status != 'ok':
            tiktok.error.throw_exception(
                response.error_code, response.error_message)
        return response

    def verify_phone(self, phone_number, code):
        response = LoginResponse(
            API('%s/passport/mobile/sms_login/' %
                TIKTOK_API[random.randint(0, 1)], self)
            .set_encoding('urlencode')
            .add_param('account_sdk_version', '380')
            .add_post('code', xorEncrypt(code))
            .add_post('account_sdk_source', 'app')
            .add_post('mix_mode', 1)
            .add_post('mobile', xorEncrypt(phone_number))
            .add_post('multi_login', 1)
            .get_response('post')
        )
        if response.status != 'ok':
            tiktok.error.throw_exception(
                response.error_code, response.error_message)
        self._update_login_state(response)
        # update temp username
        self.settings.rename(self.username, response.username)
        self._set_user(response.username)
        return self._send_login_flow(just_logged_in=True)

    def set_password(self, password):
        """
        only used once after phone number signup
        """
        resp = SetPasswordResponse(
            API('%s/passport/password/set/' % TIKTOK_API[random.randint(0, 1)], self)
            .set_encoding('urlencode')
            .add_param('account_sdk_version', '380')
            .add_post('password', xorEncrypt(password))
            .add_post('account_sdk_source', 'app')
            .add_post('mix_mode', 1)
            .add_post('multi_login', 1)
            .get_response('post')
        )
        if resp.status != 'ok':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        
        self.settings.set('pwd', password)
        return resp

    def change_username(self, username):
        '''
        :throws: UsernameTakenException
        '''
        reposnse = ChangeUsernameResponse(
            API('%s/passport/login_name/update/' %
                TIKTOK_API[random.randint(0, 1)], self)
            .set_encoding('urlencode')
            .add_post('uid', self.settings.get('user_id'))
            .add_post('page_from', 0)
            .add_post('login_name', username)
            .get_response('post')
        )
        if reposnse.status != 'ok':
            tiktok.error.throw_exception(
                reposnse.error_code, reposnse.error_message)

        # succes. don't forget to rename storage
        self.settings.rename(self.username, username)
        self._set_user(username)
        return reposnse

    def set_nickname(self, name):
        """
        name: limit 20 characters
        """
        if len(name) > 20:
            raise tiktok.error.TikTokException(
                'name cannot be longer than 20 characters')

        resp = UserResponse(
            API('%s/aweme/v1/commit/user/' % TIKTOK_API[random.randint(0, 1)], self)
            .set_encoding('urlencode')
            .add_post('uid', self.settings.get('user_id'))
            .add_post('page_from', 0)
            .add_post('nickname', name)
            .get_response('post')
        )
        if resp.status != 'ok':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def set_bio(self, bio):
        """
        bio: limit 80 characters
        """
        if len(bio) > 80:
            raise tiktok.error.TikTokException(
                'bio cannot be longer than 80 characters')
        resp = UserResponse(
            API('%s/aweme/v1/commit/user/' % TIKTOK_API[random.randint(0, 1)], self)
            .set_encoding('urlencode')
            .add_post('uid', self.settings.get('user_id'))
            .add_post('page_from', 0)
            .add_post('signature', bio)
            .get_response('post')
        )
        if resp.status != 'ok':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def set_url(self, url):
        """ 
        set account bio url. every all account is eligible to set url
        there is no error message if account is not eligible to set url
        always check resp.user.bio_url to make sure url was set
        """
        resp = UserResponse(
            API('%s/aweme/v1/commit/user/' % TIKTOK_API[random.randint(0, 1)], self)
            .set_encoding('urlencode')
            .add_post('bio_url', url)
            .add_post('uid', self.settings.get('user_id'))
            .add_post('page_from', 0)
            .add_post('school_type', 0)
            .add_post('is_binded_weibo', 0)
            .get_response('post')
        )
        if resp.status != 'ok':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp
    
    def set_biz(self):
        """ 
        """
        resp = Response(
            API('%s/aweme/v1/ad/ba/on/' % TIKTOK_API[random.randint(0, 1)], self)
            .set_encoding('urlencode')
            .add_param('request_tag_from', 'h5')
            .add_post('category_name', 'Art & Crafts')
            .add_post('category_id', 'art_crafts')
            .get_response('post')
        )
        # if resp.status != 'ok':
        #     tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def set_biz_after(self):
        """ 
        """
        api_ = (
            API('%s/aweme/v1/commit/user/' % TIKTOK_API[random.randint(0, 1)], self)
            .set_encoding('urlencode')
            .add_param('request_tag_from', 'h5')
        )
        for k,v in api_.default_params.items():
            api_.add_post(k, v)

        resp = Response(
            api_.get_response('post')
        )
        # if resp.status != 'ok':
        #     tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp


    def upload_image(self, image_path):
        return UploadImageResponse(
            API('%s/aweme/v1/upload/image/' % TIKTOK_API[random.randint(0, 1)], self)
            .set_encoding('image_upload')
            .add_param('uid', self.settings.get('user_id'))
            .add_param('retry_type', 'no_retry')
            .add_param('sec_uid', self.settings.get('sec_user_id'))
            .add_post('img_path', image_path)
            .get_response('post')
        )

    def profile_image(self, image_path):
        response = self.upload_image(image_path)
        if response.status == 'ok':
            return UserResponse(
                API('%s/aweme/v1/commit/user/' %
                    TIKTOK_API[random.randint(0, 1)], self)
                .set_encoding('urlencode')
                .add_post('uid', self.settings.get('sec_user_id'))
                .add_post('page_from', 0)
                .add_post('school_type', 0)
                .add_post('avatar_uri', response.uri)
                .add_post('is_binded_weibo', 0)
                .get_response('post')
            )
        # response not ok
        return response

    def send_email_code_v2(self, email):
        response = SendEmailCodeResponse(
            API('%s/passport/email/send_code/' %
                TIKTOK_API[random.randint(0, 1)], self)
            .add_param('mix_mode', '1')
            .add_param('email', xorEncrypt(email))
            .add_param('ticket', '')
            .add_param('type', '3d')
            .add_param('request_tag_from', 'h5')
            .get_response('get')
        )
        if response.status != 'ok':
            tiktok.error.throw_exception(
                response.error_code, response.error_message)
        return response

    def verify_email_v2(self, email, code):
        response = VerifyEmailCodeResponse(
            API('%s/passport/email/bind/' %
                TIKTOK_API[random.randint(0, 1)], self)
            .add_param('mix_mode', '1')
            .add_param('code', xorEncrypt(code))
            .add_param('email', xorEncrypt(email))
            .add_param('type', '3d')
            .add_param('request_tag_from', 'h5')
            .get_response('get')
        )
        if response.status != 'ok':
            tiktok.error.throw_exception(
                response.error_code, response.error_message)
        return response

    def disable_comment(self, video_id, setting=3):
        resp = CommentSettingsResponse(
            API('%s/aweme/v1/user/set/settings/' %
                TIKTOK_API[random.randint(0, 1)], self)
            .add_param('field', 'item_comment')
            .add_param('private_setting', setting)
            .add_param('aweme_id', video_id)
            .get_response('get')
        )
        if resp.status != 'ok':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp
    
    def enable_comment(self, video_id):
        return self.disable_comment(video_id, setting=0)

    def delete_video(self, video_id):
        resp = DeleteVideoResponse(
            API('%s/aweme/v1/aweme/delete/' %
                TIKTOK_API[random.randint(0, 1)], self)
            .add_param('aweme_id', video_id)
            .get_response('get')
        )
        if resp.status != 'ok':
            tiktok.error.throw_exception(resp.error_code, resp.error_message)
        return resp

    def custom(self, url):
        return API(url, self)

    def _temp_username(self):
        return 'temp%s' % ''.join(str(random.randint(0, 9)) for _ in range(8))


if __name__ == "__main__":
    pass