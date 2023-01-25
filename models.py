from tiktok.utils import generate_random, username_to_id
from datetime import datetime
import threading, time
import sqlite3
import json
import random
import logging
from pathlib import Path

from tiktok.error import UpdateError

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

from utils import time_int, login, DB_DIR

# d_logger = logging.getLogger('debug_models')
# d_logger.setLevel(logging.DEBUG)
# setup_logger('debug_models.log', d_logger)

class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()

        return json.JSONEncoder.default(self, o)

class Database:
    def __init__(self, name='tiktokbot.db'):
        self._conn = sqlite3.connect(f'{DB_DIR}{name}', detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
        self._cursor = self._conn.cursor()
        self.execute('PRAGMA foreign_keys = ON')
        self.execute("PRAGMA journal_mode=WAL")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.commit()
        self.cursor.close()
        self.connection.close()

    @property
    def connection(self):
        return self._conn

    @property
    def cursor(self):
        return self._cursor

    def commit(self):
        self.connection.commit()

    def execute(self, sql, params=None):
        counter = 0
        while True:
            try:
                self.cursor.execute(sql, params or ())
                break
            except sqlite3.OperationalError as e:
                counter += 1
                if counter >= 50:
                    raise
                logger.error('Error database(%s): %s' %(counter, e))
                time.sleep(random.randint(1, 2))        

    def fetchall(self):
        return self.cursor.fetchall()

    def fetchmany(self, num=0):
        return self.cursor.fetchmany(num)

    def fetchone(self):
        return self.cursor.fetchone()

    def get_data(self, sql, params=None):
        self.cursor.execute(sql, params or ())
        return self.fetchone()

    def query(self, sql, params=None):
        self.cursor.execute(sql, params or ())
        return self.fetchall()

    def create_tables(self, schema_file, recreate=False):
        if recreate:
            logger.debug('Dropping all tables')
            self.connection.executescript('''
                DROP TABLE IF EXISTS accounts;
                DROP TABLE IF EXISTS follow_schedule;
                DROP TABLE IF EXISTS follow_log;
                DROP TABLE IF EXISTS users;
            ''')

        with open(schema_file) as f:
            schema = f.read()
        logger.debug('Creating schema')
        self.connection.executescript(schema)


class DataEntry:
    def __init__(self, db='tiktokbot.db'):
        self._db_name = db
        self._params = []
        self._query = ''
        self._data = {}
        self._fields = ()
        self._table = ''
        self.is_available = False

        self._changed_fields = []  # for update

    def select(self, *, data=None, **params):
        if not data and not params:
            return self
        if params:
            self._query = 'select * from ' + self._table
            self._params = []

            for key, value in params.items():
                self.where(key, '=', value)
            
            with Database(self._db_name) as db:
                data = db.get_data(self._query, tuple(self._params))
        if data:
            self._data = dict(zip(self._fields, data))
            self.is_available = True
            data = None
        else:
            self.is_available = False
            self._data = params
        return self

    def where(self, key, op, value):
        self._query += ' {} {} {} ?'.format(
            'where' if not self._params else 'and', key, op)
        self._params.append(value)
        return self

    def get(self, key):
        key = key.split('.')
        if key[0] not in self._fields:
            raise ValueError('%s not a valid field in table %s' %
                             (key, self._table))

        try:
            if len(key) == 1:
                return self._data[key[0]]
            else:
                return self._data[key[0]][key[1]]
        except KeyError:
            return None

    def set(self, key, value, onload=False):
        ''' on_load is used to ignore on start '''
        key = key.split('.')
        if key[0] not in self._fields:
            raise ValueError('%s not a valid field in table %s' %
                             (key, self._table))

        if len(key) == 1:
            self._data[key[0]] = value
        else:
            try:
                # self._data[key[0]][key[1]]
                self._data[key[0]][key[1]] = value
            except KeyError:
                raise ValueError(
                    '%s not a valid field in table %s' % (key, self._table))

        if self.is_available and key[0] not in self._changed_fields and not onload:
            self._changed_fields.append(key[0])
        return self

    def update(self):
        if not self.is_available or len(self._changed_fields) <= 0:
            return False

        sql = 'update ' + self._table + ' set'
        for field in self._changed_fields:
            sql += ' {}=?,'.format(field)
        sql = sql.strip(',') + ' where id=?'

        data = tuple(
            json.dumps(self.get(field), cls=DateTimeEncoder) if field in ('target', 'filters', 'settings', 'data')
            else self.get(field) for field in self._changed_fields
        )
        data = data + tuple([self.get('id')])
        with Database(self._db_name) as db:
            db.execute(sql, data)
        self._changed_fields.clear()

    def insert(self):
        if self.is_available:
            return False

        sql = 'insert into ' + self._table + '('
        for field in self._fields[1:]:
            sql += f'{field}, '

        sql = sql.strip(', ') + ') values('
        for field in self._fields[1:]:
            sql += '?, '

        sql = sql.strip(', ') + ')'

        data = tuple(
            json.dumps(self.get(field), cls=DateTimeEncoder) if field in ('target', 'filters', 'settings', 'data')
            else self.get(field) for field in self._fields[1:]
        )

        with Database(self._db_name) as db:
            db.execute(sql, data)
            self.set('id', db.cursor.lastrowid)
        self.is_available = True

    def delete(self):
        if not self.is_available:
            return False
        sql = 'delete from ' + self._table + ' where id=?'
        with Database(self._db_name) as db:
            db.execute(sql, (self.get('id'),))

        # self._db.execute(sql, (self.get('id'),))
        # self._db.commit()
        self.is_available = False
        return True

    def save(self):
        if self.is_available:
            self.update()
        else:
            self.insert()
        #self._db.commit()

class DataList:
    def __init__(self, table, Model, db='tiktokbot.db'):
        self._db_name = db
        self._Model = Model
        self._params = []
        self._query = 'select * from ' + table
        self._limit = 0
        self._table = table

    def where(self, key, op, value, *args):
        if value == 'date':
            self._query += ' {} {} {} date({})'.format(
                'where' if not self._params else 'and', key, op, ('?,' * len(args)).strip(',')
            )
            self._params.extend(args)
        else:
            self._query += ' {} {} {} ?'.format(
                'where' if not self._params else 'and', key, op)
            self._params.append(value)
        return self
    
    def or_where(self, key, op, value, *args):
        if value == 'date':
            self._query += ' {} {} {} date({})'.format(
                'where' if not self._params else 'or', key, op, ('?,' * len(args)).strip(',')
            )
            self._params.extend(args)
        else:
            self._query += ' {} {} {} ?'.format(
                'where' if not self._params else 'or', key, op)
            self._params.append(value)
        return self

    def limit(self, limit):
        self._limit = limit
        return self

    def order_by(self, field, order, *args):
        self._query += ' order by ' + field + ' ' + order
        if args:
            self._query += f', {args[0]} {args[1]}'
        return self

    def count(self):
        sql = self._query.replace('*', 'count(*)')
        with Database(self._db_name) as db:
            count = db.get_data(sql, tuple(self._params))[0]
        return count

    def fetch_data(self):
        with Database(self._db_name) as db:
            db.execute(self._query, tuple(self._params))

            results = []
            counter = 0
            for row in db.cursor:
                counter += 1
                results.append(self._Model(db=self._db_name, data=row))
                
                if counter == self._limit:
                    break
        row = None
        return results

    def fetch_active_due_schedules(self):
        sql = f'select {self._table}.* from {self._table} inner join accounts on {self._table}.account_id = accounts.id \
        where {self._table}.schedule_date <=? and {self._table}.active_start <=? and {self._table}.active_end >=? and {self._table}.is_active=? and accounts.login_required=?'
        with Database(self._db_name) as db:
            now = datetime.now()
            active_time = time_int(now)
            db.execute(sql, (now, active_time, active_time, 1, 0))

            results = []
            counter = 0
            for row in db.cursor:
                counter += 1
                results.append(self._Model(data=row))
                
                if counter == self._limit:
                    break
        return results


class BaseScheduleModel(DataEntry):
    ''' schedule base class. all schedule models inherit this class '''
    _lock = threading.Lock()

    def __init__(self, table, data, db='tiktokbot.db', **params):
        super().__init__(db)
        self._table = table
        self._fields = (
            'id', 'account_id', 'target', 'filters', 'settings', 'is_active', 'tags', 'active_start', 'active_end',
            'schedule_date', 'last_action_date', 'data'
        )
        # this keeps track of a subclass instances of the schedule
        # and allow for the schedule to be disabled in the
        # middle of operation
        if not hasattr(globals()[self.__class__.__name__], '_is_disabled'):
            globals()[self.__class__.__name__]._is_disabled = {}

        self.select(data=data, **params)
        if self.is_available:
            self.set('target', json.loads(self.get('target')), onload=True)
            self.set('filters', json.loads(self.get('filters')), onload=True)
            self.set('settings', json.loads(self.get('settings')), onload=True)
            self.set('data', json.loads(self.get('data')), onload=True)

            self.is_disabled = False if self.get('is_active') else True

    def insert(self):
        self._extend_defaults()
        if super().insert():
            self.is_disabled = False if self.get('is_active') else True

    def _extend_defaults(self):
        raise NotImplementedError

    def add_source(self, target, sources):
        if not self.is_available:
            return False

        targets = self.get('target')
        if target == 'followers' or target == 'followings':
            if type(sources) is str:
                sources = [sources]

            # take care of duplicatees
            for src in targets[target]['source']:
                if src[0] in sources:
                    sources.remove(src[0])

            for source in sources:
                try:
                    user_id, user_sec_id = username_to_id(source)
                except ValueError:
                    logger.info('%s: invalid source. Failed to add %s' %
                                (self.get('account_id'), source))
                    continue
                except Exception:
                    raise
                if target == 'followers':
                    targets['followers']['source'].append(
                        [source, user_id, user_sec_id])
                else:
                    targets['followings']['source'].append(
                        [source, user_id, user_sec_id])
        elif target == 'users':
            if type(sources) is str:
                sources = [sources]

            for source in sources:
                source = source.split(',')
                targets['users']['source'].append(source)
        self.set('target', self.get('target')).save()

    def enable_target(self, target, status=1):
        if not self.is_available:
            return False
        if target not in ('followers', 'followings', 'comments', 'users', 'url_list'):
            return False

        self.get('target')[target]['status'] = status
        self.set('target', self.get('target')).save()

    def disable_target(self, target):
        self.enable_target(target, status=0)

    def enable(self, status=1):
        if not self.is_available:
            raise Exception('schedule does not exit')
        self.set('schedule_date', datetime.now())
        self.set('is_active', status).save()
        self.is_disabled = False if status else True

    def disable(self):
        self.enable(status=0)

    @property
    def is_disabled(self):
        if not self.is_available:
            raise Exception('Not available')
        return globals()[self.__class__.__name__]._is_disabled[self.get('id')]

    @is_disabled.setter
    def is_disabled(self, status):
        ''' :status: True/False '''
        if not self.is_available:
            raise Exception('Not available')
        globals()[self.__class__.__name__]._is_disabled[self.get('id')] = status
    
    def fetch_users(self):
        raise NotImplementedError

class BaseLogModel(DataEntry):
    def __init__(self, table, fields, data=None, db='tiktokbot.db', **params):
        super().__init__(db)
        self._table = table
        self._fields = fields

        self.select(data=data, **params)
        if self.is_available:
            self.set('data', json.loads(self.get('data')), onload=True)

    def insert(self):
        self._extend_defaults()
        super().insert()

    def _extend_defaults(self):
        raise NotImplementedError



class AccountModel(DataEntry):
    def __init__(self, *, db='tiktokbot.db', data=None, **params):
        super().__init__(db)
        self._table = 'accounts'
        self._fields = (
            'id', 'username', 'password', 'email', 'phone', 'user_id', 'user_sec_id', 'proxy', 'active_start',
            'active_end', 'last_login', 'last_action_date', 'added_date', 'tags', 'data', 'login_required'
        )
        self.select(data=data, **params)
        if self.is_available:
            self.set('data', json.loads(self.get('data')), onload=True)
        self._tik = None

    def Tik(self, folder=None, no_proxy=True, login_flow=False):
        if not self.is_available:
            raise Exception('Error!')
        if not self._tik:
            self._tik = login(self, folder=folder, no_proxy=no_proxy, login_flow=login_flow)
        return self._tik

    def insert(self):
        self._extend_defaults()
        super().insert() 

    def set_bio(self, bio=None):
        if not self.is_available:
            return False
        
        if not bio:
            bio = 'GET 💯 FREE TIKTOK FOLLOWERS 🔥🔥 VISIT 🌐 👉👉 free4tiktok.com 👇👇'
        try:
            self.Tik().set_bio(bio)
            print('%s bio set' %self.get('username'))
        except Exception as e:
            print('%s: Setting Bio Error: %s' %(self.get('username'), e))
    
    def set_nickname(self, text=None):
        if not self.is_available:
            return False

        nk = [
            '🔥TIKTOK F0LLOWERS', '🔥GAIN F0LLOWERS📍', '📌GAIN F0LLOWERS📌', 
            '😍GAIN F0LLOWERS😍', '❣️❣️GAIN F0LLOWERS❣️', '💥GAIN F0LLOWERS💥', 
            '📲GAIN F0LLOWERS✔️', '📌TIKTOK F0LLOWERS', '🔥TIKTOK F0LLOWERS', 
            '📲TIKTOK F0LLOWERS', '💥TIKTOK F0LLOWERS', '😍TIKTOK F0LLOWERS', 
            '❣️TIKTOK F0LLOWERS❣️', '🎉 TIKTOK F0LLOWERS', '🎉 GAIN F0LLOWERS🎉']
        if not text:
            text = random.choice(nk)
            
        try:
            self.Tik().set_nickname(text)
            print('%s nickname set' %self.get('username'))
        except Exception as e:
            print('%s: Setting nickname Error: %s' %(self.get('username'), e))

    def set_url(self, url):
        if not self.is_available:
            return False
        
        self.set('data.url', url).save()
        try:
            resp = self.Tik(no_proxy=True).set_url(url)
            if resp.user.bio_url:
                print('%s url %s set' % (self.get('username'), url))
            else:
                print('%s failed to add url: %s' %(self.get('username'), url))
        except UpdateError:
            print('%s: Setting url %s error. Blocked' %(self.get('username'), url))
            self.set('data.err_msg', 'url blocked').save()
        except Exception as e:
            print('%s: Setting url %s error: %s' %(self.get('username'), url, e))

    def _extend_defaults(self):
        defaults = {
            'id': 0,
            'username': 'tiktok_' + generate_random(),
            'password': generate_random(),
            'email': '',
            'phone': '',
            'user_id': 0,
            'user_sec_id': '',
            'proxy': '',
            'active_start': 0,
            'active_end': 2359,
            'last_login': datetime.now(),
            'last_action_date': datetime.now(),
            'added_date': datetime.now(),
            'tags': '',
            'data': {
                'follow_failed': 0,
                'like_failed': 0,
                'comment_failed': 0,
                'error': 0,
                'url': '',
            },
            'login_required': 1
        }

        for field in self._fields:
            if self.get(field) == 0:
                continue
            if not self.get(field):
                self.set(field, defaults.get(field))

class DeviceModel(DataEntry):
    def __init__(self, *, db='devices.db', data=None, **params):
        super().__init__(db=db)
        self._table = 'device'
        self._fields = (
            'id', 'device_string', 'google_aid', 'openudid', 'uuid', 'device_id', 'install_id',
            'used_count', 'last_action_date', 'added_date', 'tags', 'data'
        )
        self.select(data=data, **params)
        if self.is_available:
            self.set('data', json.loads(self.get('data')), onload=True)

    def insert(self):
        self._extend_defaults()
        super().insert() 

    def _extend_defaults(self):
        defaults = {
            'id': 0,
            'device_string': '',
            'google_aid': '',
            'openudid': '',
            'uuid': '',
            'device_id': '',
            'install_id': '',
            'used_count': 0,
            'last_action_date': datetime.now(),
            'added_date': datetime.now(),
            'tags': '',
            'data': {
                'follow_fail': 0,
                'follow_success': 0,
                'comment_success': 0,
                'comment_fail': 0,
                'last_success_date': 0
            },
        }

        for field in self._fields:
            if self.get(field) == 0:
                continue
            if not self.get(field):
                self.set(field, defaults.get(field))

class ProxyModel(DataEntry):
    def __init__(self, *, db='tiktokbot.db', data=None, **params):
        super().__init__(db)
        self._table = 'proxies'
        self._fields = (
            'id', 'proxy', 'port', 'username', 'password', 'used_count',
            'rotate', 'last_action_date', 'added_date', 'tags', 'data'
        )
        self.select(data=data, **params)
        if self.is_available:
            self.set('data', json.loads(self.get('data')), onload=True)

    def insert(self):
        self._extend_defaults()
        super().insert() 

    def get_proxy(self):
        if not self.is_available:
            return None
        
        if self.get('username') and self.get('password'):
            return '{}:{},{},{}'.format(
                self.get('proxy'),
                self.get('port'),
                self.get('username'),
                self.get('password')
            )
        else:
            return '{}:{}'.format(
                self.get('proxy'), self.get('port')
            )

    def _extend_defaults(self):
        defaults = {
            'id': 0,
            'proxy': '',
            'port': '',
            'username': '',
            'password': '',
            'used_count': 0,
            'rotate': 0,
            'last_action_date': datetime.now(),
            'added_date': datetime.now(),
            'tags': '',
            'data': {
                'error': 0
            },
        }

        for field in self._fields:
            if self.get(field) == 0:
                continue
            if not self.get(field):
                self.set(field, defaults.get(field))



class FollowScheduleModel(BaseScheduleModel):
    ''' the auto follow schedule '''

    def __init__(self, *, db='tiktokbot.db', data=None, **params):
        super().__init__('follow_schedule', data, db, **params)

    def _extend_defaults(self):
        defaults = {
            'id': 0,
            'account_id': 0,
            'target': {
                'followers': {'source': [], 'status': 0},
                'followings': {'source': [], 'status': 0},
                'comments': {'source': [], 'status': 0},
                'users': {'source': [], 'status': 0}
            },
            'filters': {
                'max_followers': 1000,
                'filter_max_followers': 0,
                'max_followings': 1000,
                'filter_max_followings': 0,
                'blacklist_words': [],
                'filter_blacklist': 0,
                'profile_pic': 0,
                'verified': 0,
                'unique_accross': 1,
            },
            'settings': {
                'max_per_day': 100,
                'sleep_min': 15,
                'sleep_max': 30,
                'follows_per_op_min': 10,
                'follows_per_op_max': 15,
                'next_op_min': 10,
                'next_op_max': 20,
            },
            'is_active': 0,
            'tags': '',
            'active_start': 0,
            'active_end': 2359,
            'schedule_date': datetime.now(),
            'last_action_date': datetime.now(),
            'data': {
                'users': [],
                'target': {}
            }
        }
        for field in self._fields:
            if self.get(field) == 0:
                continue
            if not self.get(field):
                self.set(field, defaults.get(field))

    def fetch_users(self, limit=20, followers_filter=20000):
        # sql = f'select id,username,user_id,user_sec_id from users where is_fetched=0 \
        #     and follower_count < ? order by added_date ASC limit {limit}'
        sql = f'select id,username,user_id,user_sec_id from users where is_fetched=0 \
            and follower_count < ? limit {limit}'
        with BaseScheduleModel._lock:
            with Database('tiktok_users.db') as db:
                db.execute(sql, (followers_filter,))
                users = db.fetchall()

                # update fetched rows is_fetched col to 1
                if len(users) > 0:
                    data = [(1, row[0]) for row in users]
                    
                    error_counter = 0
                    while True:
                        try:
                            db.cursor.executemany('update users set is_fetched=? where id=?', data)
                            break
                        except sqlite3.OperationalError as e:
                            logger.error('Follow schdule id: %s: %s. Counter: %s' %(self.get('id'), e, error_counter))
                            error_counter += 1
                            if error_counter >= 50:
                                raise
                            time.sleep(random.randint(2, 3))
        return [row[1:] for row in users]
    
class VideoLikeScheduleModel(BaseScheduleModel):
    ''' the auto video like schedule '''

    def __init__(self, *, db='tiktokbot.db', data=None, **params):
        super().__init__('video_like_schedule', data, db, **params)

    def _extend_defaults(self):
        defaults = {
            'id': 0,
            'account_id': 0,
            'target': {
                'followers': {'source': [], 'status': 0},
                'followings': {'source': [], 'status': 0},
                'comments': {'source': [], 'status': 0},
                'users': {'source': [], 'status': 0},
                'url_list': {'source': [], 'status': 0}
            },
            'filters': {
                'max_followers': 1000,
                'filter_max_followers': 0,
                'max_followings': 1000,
                'filter_max_followings': 0,
                'blacklist_words': [],
                'filter_blacklist': 0,
                'verified': 0,
                'unique_accross': 1,
                'max_views': 10000,
                'filter_max_views': 0
            },
            'settings': {
                'max_actions_per_day': 750,
                'sleep_min': 15,
                'sleep_max': 30,
                'actions_per_op_min': 10,
                'actions_per_op_max': 15,
                'next_schedule_min': 6,
                'next_schedule_max': 12,
                'like_per_user': 3,  # max videos to like per user
            },
            'is_active': 0,
            'tags': '',
            'active_start': 0,
            'active_end': 2359,
            'schedule_date': datetime.now(),
            'last_action_date': datetime.now(),
            'data': {
                'users': [],
                'target': {}
            }
        }
        for field in self._fields:
            if self.get(field) == 0:
                continue
            if not self.get(field):
                self.set(field, defaults.get(field))

    def fetch_users(self, limit=20):
        # sql = f'select id,username,user_id,user_sec_id from users where is_fetched=0 \
        #     and video_count > 0 and is_private = 0 order by added_date ASC limit {limit}'
            
        sql = f'select id,username,user_id,user_sec_id from users where is_fetched=0 \
            and video_count > 0 and is_private = 0 limit {limit}'
        with BaseScheduleModel._lock:
            with Database('tiktok_users.db') as db:
                db.execute(sql)
                users = db.fetchall()

                # update fetched rows is_fetched col to 1
                if len(users) > 1:
                    data = [(1, row[0]) for row in users]

                    error_counter = 0
                    while True:
                        try:
                            db.cursor.executemany('update users set is_fetched=? where id=?', data)
                            break
                        except sqlite3.OperationalError as e:
                            logger.error('Follow schdule id: %s: %s. Counter: %s' %(self.get('id'), e, error_counter))
                            error_counter += 1
                            if error_counter >= 50:
                                raise
                            time.sleep(random.randint(2, 3))

        # return list of username,user_id,user_sec_id
        return [row[1:] for row in users]

class CommentScheduleModel(BaseScheduleModel):
    ''' the auto comment schedule '''

    def __init__(self, *, db='tiktokbot.db', data=None, **params):
        super().__init__('comment_schedule', data, db, **params)

    def _extend_defaults(self):
        defaults = {
            'id': 0,
            'account_id': 0,
            'target': {
                'followers': {'source': [], 'status': 0},
                'followings': {'source': [], 'status': 0},
                'comments': {'source': [], 'status': 0},
                'users': {'source': [], 'status': 0}
            },
            'filters': {
                'max_followers': 1000,
                'filter_max_followers': 0,
                'max_followings': 1000,
                'filter_max_followings': 0,
                'blacklist_words': [],
                'filter_blacklist': 0,
                'profile_pic': 0,
                'verified': 0,
                'unique_accross': 1,
            },
            'settings': {
                'max_per_day': 500,
                'sleep_min': 10,
                'sleep_max': 30,
                'op_min': 10,
                'op_max': 15,
                'next_op_min': 10,
                'next_op_max': 20,
                'comment_per_user': 3
            },
            'is_active': 0,
            'tags': '',
            'active_start': 0,
            'active_end': 2359,
            'schedule_date': datetime.now(),
            'last_action_date': datetime.now(),
            'data': {
                'users': [],
                'target': {}
            }
        }
        for field in self._fields:
            if self.get(field) == 0:
                continue
            if not self.get(field):
                self.set(field, defaults.get(field))
        
    def fetch_users(self, limit=20, followers_min=1, followers_max=2000000):
        sql = f'select id,username,user_id,user_sec_id from users where is_fetched=0 \
            and video_count > 0 and is_private = 0 order by added_date DESC limit {limit}'
        with BaseScheduleModel._lock:
            with Database('tiktok_users.db') as db:
                db.execute(sql)
                users = db.fetchall()

                # update fetched rows is_fetched col to 1
                if len(users) > 1:
                    data = [(1, row[0]) for row in users]

                    error_counter = 0
                    while True:
                        try:
                            db.cursor.executemany('update users set is_fetched=? where id=?', data)
                            break
                        except sqlite3.OperationalError as e:
                            logger.error('Follow schdule id: %s: %s. Counter: %s' %(self.get('id'), e, error_counter))
                            error_counter += 1
                            if error_counter >= 50:
                                raise
                            time.sleep(random.randint(2, 3))
        return [row[1:] for row in users]

class UnFollowScheduleModel(BaseScheduleModel):
    ''' the auto unfollow schedule '''

    def __init__(self, *, db='tiktokbot.db', data=None, **params):
        super().__init__('unfollow_schedule', data, db, **params)

    def _extend_defaults(self):
        defaults = {
            'id': 0,
            'account_id': 0,
            'target': {},
            'filters': {
                'max_days': 5,
            },
            'settings': {
                'max_per_day': 1500,
                'sleep_min': 5,
                'sleep_max': 10,
                'unfollows_per_op_min': 20,
                'unfollows_per_op_max': 30,
                'next_op_min': 5,
                'next_op_max': 10,
                'stop_at': 500,
            },
            'is_active': 0,
            'tags': '',
            'active_start': 0,
            'active_end': 2359,
            'schedule_date': datetime.now(),
            'last_action_date': datetime.now(),
            'data': {
                'max_time': 0,
                'offset': 0,
                'following_count': 0,
            }
        }
        for field in self._fields:
            if self.get(field) == 0:
                continue
            if not self.get(field):
                self.set(field, defaults.get(field))



class FollowLogModel(BaseLogModel):
    def __init__(self, *, db='tiktokbot.db', data=None, **params):
        fields = (
            'id', 'account_id', 'status', 'user_id', 'user_sec_id', 'data', 'followed_date',
        )
        super().__init__('follow_log', fields, data, db, **params)

    def _extend_defaults(self):
        defaults = {
            'id': 0,
            'account_id': 0,
            'status': 'fail',
            'user_id': 0,
            'user_sec_id': '',
            'data': {
                "followed": {
                    "username": ""
                }, 
                "target": {
                    "type": ""
                }
            },
            'followed_date': datetime.now()
        }

        for field in self._fields:
            if self.get(field) == 0:
                continue
            if not self.get(field):
                self.set(field, defaults.get(field))

class VideoLikeLogModel(BaseLogModel):
    def __init__(self, *, db='tiktokbot.db', data=None, **params):
        fields = (
            'id', 'account_id', 'status', 'user_id', 'user_sec_id', 'video_id', 'data', 'liked_date',
        )
        super().__init__('video_like_log', fields, data, db, **params)

    def _extend_defaults(self):
        defaults = {
            'id': 0,
            'account_id': 0,
            'status': 'fail',
            'user_id': 0,
            'user_sec_id': '',
            'video_id': 0,
            'data': {},
            'liked_date': datetime.now()
        }

        for field in self._fields:
            if self.get(field) == 0:
                continue
            if not self.get(field):
                self.set(field, defaults.get(field))

class CommentLogModel(BaseLogModel):
    def __init__(self, *, db='tiktokbot.db', data=None, **params):
        fields = (
            'id', 'account_id', 'status', 'user_id', 'user_sec_id', 'video_id', 'comment_id', 'comment', 'data', 'commented_date',
        )
        super().__init__('comment_log', fields, data, db, **params)

    def _extend_defaults(self):
        defaults = {
            'id': 0,
            'account_id': 0,
            'status': 'fail',
            'user_id': 0,
            'user_sec_id': '',
            'video_id': 0,
            'comment_id': 0,
            'comment': '',
            'data': {},
            'commented_date': datetime.now()
        }

        for field in self._fields:
            if self.get(field) == 0:
                continue
            if not self.get(field):
                self.set(field, defaults.get(field))

class UnFollowLogModel(BaseLogModel):
    def __init__(self, *, db='tiktokbot.db', data=None, **params):
        fields = (
            'id', 'account_id', 'status', 'user_id', 'user_sec_id', 'data', 'unfollowed_date',
        )
        super().__init__('unfollow_log', fields, data, db, **params)

    def _extend_defaults(self):
        defaults = {
            'id': 0,
            'account_id': 0,
            'status': 'fail',
            'user_id': 0,
            'user_sec_id': '',
            'data': {},
            'unfollowed_date': datetime.now()
        }

        for field in self._fields:
            if self.get(field) == 0:
                continue
            if not self.get(field):
                self.set(field, defaults.get(field))



class AccountsModel(DataList):
    def __init__(self, db='tiktokbot.db'):
        super().__init__('accounts', AccountModel, db)

class DevicesModel(DataList):
    def __init__(self, db='devices.db'):
        super().__init__('device', DeviceModel, db)

class ProxiesModel(DataList):
    def __init__(self, db='tiktokbot.db'):
        super().__init__('proxies', ProxyModel, db)

class FollowSchedulesModel(DataList):
    def __init__(self, db='tiktokbot.db'):
        super().__init__('follow_schedule', FollowScheduleModel, db)

class FollowLogsModel(DataList):
    def __init__(self, db='tiktokbot.db'):
        super().__init__('follow_log', FollowLogModel, db)

class VideoLikeSchedulesModel(DataList):
    def __init__(self, db='tiktokbot.db'):
        super().__init__('video_like_schedule', VideoLikeScheduleModel, db)

class VideoLikeLogsModel(DataList):
    def __init__(self, db='tiktokbot.db'):
        super().__init__('video_like_log', VideoLikeLogModel, db)

class CommentSchedulesModel(DataList):
    def __init__(self, db='tiktokbot.db'):
        super().__init__('comment_schedule', CommentScheduleModel, db)

class CommentLogsModel(DataList):
    def __init__(self, db='tiktokbot.db'):
        super().__init__('comment_log', CommentLogModel, db)
        
class UnFollowSchedulesModel(DataList):
    def __init__(self, db='tiktokbot.db'):
        super().__init__('unfollow_schedule', UnFollowScheduleModel, db)

class UnFollowLogsModel(DataList):
    def __init__(self, db='tiktokbot.db'):
        super().__init__('unfollow_log', UnFollowLogModel, db)