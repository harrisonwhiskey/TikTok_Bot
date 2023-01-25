class TikTokException(Exception):
    pass

class CaptchaErrorException(Exception):
    pass

class InvalidAccountException(Exception):
    pass

class BadRequestException(Exception):
    pass

class AndroidDeviceError(Exception):
    pass

class UsernameTakenException(Exception):
    pass

class UsernameError(Exception):
    pass

class EmailErrorException(Exception):
    pass

class IncorrectCodeException(Exception):
    pass

class InvalidPasswordException(Exception):
    pass

class AccountDisabledException(Exception):
    pass

class TooMuchRequestException(Exception):
    pass

class FollowFailedException(Exception):
    pass

class LikeFailedException(Exception):
    pass

class CantFollowUserException(Exception):
    pass

class PassWordSetException(Exception):
    pass

class CommentException(Exception):
    pass

class LikeVideoError(Exception):
    pass

class ServerError(Exception):
    pass

class InvalidOperationException(Exception):
    pass

class CommentBlockedException(Exception):
    pass

class FollowLimitReached(Exception):
    pass

class LoginExpiredException(Exception):
    pass

class UserNotExit(Exception):
    pass

class VideoNotExist(Exception):
    pass

class CommentGhosted(Exception):
    pass

class ProfileUpdateBlocked(Exception):
    pass

class UpdateError(Exception):
    pass

def throw_exception(error_code, message=''):
    error_code = int(error_code)
    if error_code in (1009, 1011):
        raise InvalidAccountException(message)
    elif error_code == 1105:
        raise CaptchaErrorException('You need to solve a captcha')
    elif error_code == 7:
        # visiting our service too frequently
        # cause: blocked device info / invalid X-Gorgon
        raise BadRequestException(message + ' Cause: bad device info / invalid X-Gorgon')
    elif error_code in (4, 999):
        raise ServerError(message)
    elif error_code == 1024:
        raise UsernameTakenException(message)
    elif error_code in (1202, 1203):
        raise IncorrectCodeException(message)
    elif error_code == 1051:
        raise InvalidPasswordException(message)
    elif error_code in (1023, 1031):
        raise EmailErrorException(message)
    elif error_code in (2149, 2150, 2147):
        raise TooMuchRequestException(message)
    elif error_code == 901:
        raise FollowFailedException(message)
    elif error_code == 9001:
        raise LikeFailedException(message)
    elif error_code == 1330:
        raise UsernameError(message)
    elif error_code in (2067, 2065, 24, 2059):
        raise CantFollowUserException(message)
    elif error_code == 9:
        raise AccountDisabledException(message)
    elif error_code in (5, 8):
        raise LoginExpiredException(message)
    elif error_code == 22:
        raise CommentBlockedException(message)
    elif error_code == 1046:
        raise PassWordSetException(message)
    elif error_code in (3057, 3056):
        raise CommentException(message)
    elif error_code == 888:
        raise CommentGhosted(message)
    elif error_code == 3050:
        raise VideoNotExist(message)
    elif error_code in (2096, 2209):
        raise InvalidOperationException(message)
    elif error_code == 2075:
        raise FollowLimitReached(message)
    elif error_code in (25, 3170):
        raise UserNotExit(message)
    elif error_code == 23:
        raise ProfileUpdateBlocked(message)
    elif error_code == 2097:
        raise UpdateError(message)
    else:
        raise TikTokException(
            'error code: {}. message: {}'.format(error_code, message))
