from pathlib import Path
import json
import shutil

from .utils import create_folder
from .constants import SRC_DIR

class Storage:
    SETTINGS_FILE = '{}-settings.dat'
    COOKIES_FILE = '{}-cookies.dat'

    PERSISTENT_KEYS = [
        'username',
        'phone',
        'email',
        'pwd',
        'device_string',
        'device_id',
        'uuid',
        'install_id',
        'google_aid',
        'openudid',
        'X-Tt-Token',
        'X-Tt-Token-Sign',
        'X-Tt-Multi-Sids',
        'user_id',
        'session_key',
        'sec_user_id',
        'proxy'
    ]
    
    def __init__(self, storage_path=None):
        self._cookies_file = None
        self._settings_file = None
        self._user_folder = None
        self._username = None
        self._user_settings = {}    # settings dict
        self._user_cookies = {}     # cookies dict
        self._default_settings()

        if storage_path:
            if ':' in storage_path:
                # absolute path
                self._base_folder = Path(storage_path)
            else:
                self._base_folder = Path(SRC_DIR) / storage_path
        else:
            self._base_folder = Path(SRC_DIR) / 'sessions'
        create_folder(self._base_folder)

    def set_user(self, username):
        if self._username == username:
            return

        if username != self._username:
            # If we are switching account 
            # remember to save current user cookies / stuff
            # TODO
            pass
        self._username = username
        self._open_user(username)
        self._load_user_settings()
        self._load_user_cookies()

    def set(self, key, value):
        if key not in Storage.PERSISTENT_KEYS:
            raise KeyError('Key: {} is not in PERSISTENT_KEYS'.format(key))
        
        if self._user_settings.get(key) != value and value is not None:
            self._user_settings[key] = value
            
            if key != 'proxy':
                self._save_user_settings()

    def get(self, key):
        if key not in Storage.PERSISTENT_KEYS:
            raise KeyError('Key: {} is not in PERSISTENT_KEYS'.format(key))

        return self._user_settings.get(key, '')

    def delete(self, username=None):
        if not username:
            username = self._username
        
        user_folder = self._generate_paths(username)['user_folder']
        if Path(user_folder).exists():
            shutil.rmtree(user_folder, ignore_errors=True)

    def _default_settings(self):
        for key in Storage.PERSISTENT_KEYS:
            self._user_settings[key] = ''

    def _generate_paths(self, username):
        paths = {}
        paths['user_folder'] = Path(self._base_folder / username)
        paths['settings_file'] = paths['user_folder'] / Storage.SETTINGS_FILE.format(username)
        paths['cookies_file'] = paths['user_folder'] /  Storage.COOKIES_FILE.format(username)
        return paths
    
    def _open_user(self, username):
        user_paths = self._generate_paths(username)
        self._user_folder = user_paths['user_folder']
        self._settings_file = user_paths['settings_file']
        self._cookies_file = user_paths['cookies_file']

        create_folder(self._user_folder)
    
    def _load_user_settings(self):
        if Path(self._settings_file).is_file():
            with open(self._settings_file, 'r') as f:
                self._user_settings = json.load(f)
        else:
            self._default_settings()

    def _save_user_settings(self):
        with open(self._settings_file, 'w') as f:
            f.write(json.dumps(self._user_settings))
    
    def _load_user_cookies(self, delete_on_error=True):
        if Path(self._cookies_file).is_file():
            try:
                with open(self._cookies_file, 'r') as f:
                    self._user_cookies = json.load(f)
            except json.decoder.JSONDecodeError:
                if delete_on_error:
                    Path(self._cookies_file).unlink()
                    self._user_cookies = {}
                else:
                    raise
        else:
            self._user_cookies = {}

    def has_user(self, username):
        user_paths = self._generate_paths(username)
        return Path(user_paths['settings_file']).is_file()

    def _save_user_cookies(self):
        with open(self._cookies_file, 'w') as f:
            f.write(json.dumps(self._user_cookies))

    def set_cookie(self, key, value):
        try:
            if self._user_cookies[key] != value:
                self._user_cookies[key] = value
                self._save_user_cookies()
        except KeyError:
            self._user_cookies[key] = value
            self._save_user_cookies()

    def get_cookies(self):
        return self._user_cookies
    
    def rename(self, old_username, new_username):
        if not self.has_user(old_username):
            raise Exception
        if old_username == new_username:
            return
        old_paths = self._generate_paths(old_username)
        new_paths = self._generate_paths(new_username)

        # rename user folder
        old_paths['user_folder'].rename(new_paths['user_folder'])

        # update old files with new user folder
        old_paths['settings_file'] = new_paths['user_folder'] / old_paths['settings_file'].parts[-1]
        old_paths['cookies_file'] = new_paths['user_folder'] / old_paths['cookies_file'].parts[-1]

        # rename files
        old_paths['settings_file'].rename(new_paths['settings_file'])
        old_paths['cookies_file'].rename(new_paths['cookies_file'])

        self._open_user(new_username)
        self.set('username', new_username)
