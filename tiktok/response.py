import logging

from .models import UserInfo, CommentInfo, VideoInfo

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class Response:
    """
    Something to write home about
    """
    STATUS_OK = 'ok'
    STATUS_FAIL = 'fail'

    def __init__(self, raw):
        """
        :raw: requests response
        """
        self.status = Response.STATUS_FAIL
        self._error_code = ''
        self._error_message = ''

        try:
            self.body = raw.json()
        except Exception:
            logger.error('Response body is not json decodable. -> %s' %(raw.text))
            self.body = {}
        self.headers = raw.headers

    @property
    def error_code(self):
        if self._error_code:
            return self._error_code

        try:
            self._error_code = self.body['data']['error_code']
            self._error_message = self.body['data']['description']
            return self._error_code
        except KeyError:
            pass

        try:
            self._error_code = self.body['status_code']
            if self._error_code == 2055:
                self._error_message = 'Comment does not exist'
            elif self._error_code == 2060:
                self._error_message = 'X-Gorgon wrong!!!: ' + \
                    self.body['status_msg']
            else:
                try:
                    # could be chinese
                    self._error_message = self.body['status_msg']
                except KeyError:
                    pass
            return self._error_code
        except KeyError:
            pass

        # error response body don't meet any of the expected
        self._error_code = 9999
        return self._error_code

    @property
    def error_message(self):
        # error response body don't meet any of the expected
        if self.error_code >= 9000:
            return self.body
        if self.error_code == 888:
            return 'comment ghosted'
        return self._error_message


class LoginResponse(Response):
    def __init__(self, response_body):
        super().__init__(response_body)

        if self.body.get('message') == 'success':
            self.status = FollowUserResponse.STATUS_OK
            self.user_id = self.body['data']['user_id']
            self.username = self.body['data']['name']
            self.session_key = self.body['data']['session_key']
            self.sec_user_id = self.body['data']['sec_user_id']
            self.new_user = self.body['data']['new_user'] == 1


class FollowUserResponse(Response):
    def __init__(self, response_body):
        super().__init__(response_body)

        # if follow_status == 4: is private user therefore watch_status will be off
        # 2: means user is already following u
        if self.body.get('follow_status') in (2, 4) or (self.body.get('follow_status') and self.body.get('watch_status')):
            self.status = FollowUserResponse.STATUS_OK
        elif self.body.get('watch_status') == 0:
            # follow failed, device flagged or account flagged. needs further investigation
            self._error_code = 901  # madeup error code for throwing the appropriate exception


class UnFollowUserResponse(Response):
    def __init__(self, response_body):
        super().__init__(response_body)

        if self.body.get('status_code') == 0 and self.body.get('follow_status') == 0:
            self.status = FollowUserResponse.STATUS_OK


class LikeVideoResponse(Response):
    def __init__(self, raw):
        super().__init__(raw)
        if self.body.get('status_code') == 0 and self.body.get('is_digg') == 0:
            self.status = LikeVideoResponse.STATUS_OK
        elif self.body.get('is_digg') == 1:
            # like not registered
            self._error_code = 9001


class LikeCommentResponse(Response):
    def __init__(self, raw):
        super().__init__(raw)
        if self.body.get('status_code') == 0:
            self.status = LikeCommentResponse.STATUS_OK


class CommentResponse(Response):
    def __init__(self, raw):
        super().__init__(raw)
        # if self.body.get('status_code') == 0 and 'successfully' in self.body.get('status_msg').lower():
        #     self.status = CommentResponse.STATUS_OK
        #     self.comment = CommentInfo(self.body['comment'])
        # print(self.body)
        if self.body.get('status_code') == 0 and self.body.get('comment').get('status') != 2:
            self.status = CommentResponse.STATUS_OK
            self.comment = CommentInfo(self.body['comment'])
        else:
            if self.body.get('status_code') == 0:
                self.body['status_code'] = 888
                # print('comment ghosted')


class CommentSettingsResponse(Response):
    def __init__(self, response_body):
        super().__init__(response_body)
        if self.body.get('status_code') == 0:
            self.status = CommentSettingsResponse.STATUS_OK


class DeleteVideoResponse(Response):
    def __init__(self, response_body):
        super().__init__(response_body)
        if self.body.get('status_code') == 0:
            self.status = DeleteVideoResponse.STATUS_OK
            

class UserResponse(Response):
    def __init__(self, raw):
        super().__init__(raw)
        if self.body.get('status_code') == 0:
            self.status = UserResponse.STATUS_OK
            self.user = UserInfo(self.body['user'])


class UploadImageResponse(Response):
    def __init__(self, raw):
        super().__init__(raw)
        if self.body.get('status_code') == 0:
            self.status = UploadImageResponse.STATUS_OK
            self.url = self.body['data']['url_list'][0]
            self.uri = self.body['data']['uri']


class UserVideoListResponse(Response):
    def __init__(self, raw):
        super().__init__(raw)
        if self.body.get('status_code') == 0:
            self.status = UserVideoListResponse.STATUS_OK
            self.has_more = self.body.get('has_more') == 1
            self.min_cursor = self.body.get('min_cursor')
            self.max_cursor = self.body.get('max_cursor')
            if self.body.get('aweme_list'):
                self.videos = [VideoInfo(data) for data in self.body.get('aweme_list')]
            else:
                self.videos = []

    @property
    def big_list(self):
        return self.body.get('aweme_list')


class FollowersFollowingsResponse(Response):
    def __init__(self, raw):
        super().__init__(raw)
        if self.body.get('status_code') == 0:
            self.status = FollowersFollowingsResponse.STATUS_OK
            self.has_more = int(self.body['has_more']) == 1
            self.rec_has_more = int(self.body['rec_has_more']) == 1
            self.min_time = self.body['min_time']
            self.max_time = self.body['max_time']
            self.total = self.body['total']
            self.offset = self.body['offset']
            try:
                self.users = [UserInfo(data)
                              for data in self.body['followings']]
            except KeyError:
                self.users = [UserInfo(data)
                              for data in self.body['followers']]
    @property
    def big_list(self):
        try:
            return self.body['followings']
        except KeyError:
            return self.body['followers']


class CheckInResponse(Response):
    def __init__(self, response_body):
        super().__init__(response_body)
        if self.body.get('status_code') == 0:
            self.status = CheckInResponse.STATUS_OK


class ShareResponse(Response):
    def __init__(self, response_body):
        super().__init__(response_body)
        if self.body.get('status_code') == 0:
            self.status = ShareResponse.STATUS_OK


class SendSmsCodeResponse(Response):
    # error_code: 1203 - incorrect code
    def __init__(self, raw):
        super().__init__(raw)
        if self.body.get('message') == 'success':
            self.status = SendSmsCodeResponse.STATUS_OK
            self.mobile_ticket = self.body['data']['mobile_ticket']


class SendEmailCodeResponse(Response):
    def __init__(self, raw):
        super().__init__(raw)
        if self.body.get('message') == 'success':
            self.status = SendSmsCodeResponse.STATUS_OK


class VerifyEmailCodeResponse(Response):
    def __init__(self, raw):
        super().__init__(raw)
        if self.body.get('message') == 'success':
            self.status = SendSmsCodeResponse.STATUS_OK
            

class SetPasswordResponse(Response):
    # error_code: 1046 - password already set
    def __init__(self, raw):
        super().__init__(raw)
        if self.body.get('message') == 'success':
            self.status = SetPasswordResponse.STATUS_OK


class ChangeUsernameResponse(Response):
    # error_code: 1024 - username already taken
    def __init__(self, raw):
        super().__init__(raw)
        if self.body.get('message') == 'success':
            self.status = ChangeUsernameResponse.STATUS_OK


class CheckEmailResponse(Response):
    def __init__(self, raw):
        super().__init__(raw)
        if self.body.get('message') == 'success':
            self.status = CheckEmailResponse.STATUS_OK
            self.is_registered = self.body['data']['is_registered'] == 1

