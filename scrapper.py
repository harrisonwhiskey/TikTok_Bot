import logging
import time
import threading
from sqlite3 import OperationalError
from random import randint
from json import loads, dumps
from datetime import datetime
from concurrent import futures
from functools import reduce
import requests

from tiktok.tiktok import TikTok
from tiktok.utils import username_to_id
import tiktok.error

from models import Database, AccountModel, AccountsModel, DataEntry, DataList, ProxiesModel
from utils import setup_logger, login, device_manager, time_int, set_new_proxy
from app import add_account


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
setup_logger('scrapper.log', logger)


class SourceModel(DataEntry):
    def __init__(self, *, db='tiktok_users.db', data=None, **params):
        super().__init__(db)
        self._table = 'source'
        self._fields = (
            'id', 'username', 'user_id', 'user_sec_id', 'follower_count', 'following_count',
            'status', 'last_activity', 'added_date', 'data'
        )
        self.select(data=data, **params)
        if self.is_available:
            self.set('data', loads(self.get('data')), onload=True)

    def insert(self):
        self._extend_defaults()
        super().insert()

    def _extend_defaults(self):
        defaults = {
            'id': 0,
            'username': '',
            'user_id': 0,
            'user_sec_id': '',
            'follow_count': 0,
            'following_count': 0,
            'status': 1,
            'last_activity': datetime.now(),
            'added_date': datetime.now(),
            'data': {
                'followers_offset': 0,
                'followers_has_more': 1,
                'followings_offset' : 0,
                'followings_has_more': 1,
                'max_time': 0,
                'min_time': 0,
            },
        }

        for field in self._fields:
            if self.get(field) == 0:
                continue
            if not self.get(field):
                self.set(field, defaults.get(field))

class SourcesModel(DataList):
    def __init__(self):
        super().__init__('source', SourceModel, 'tiktok_users.db')


class DailySourceModel(DataEntry):
    def __init__(self, *, data=None, **params):
        super().__init__(db='tiktok_users.db')
        self._table = 'daily_source'
        self._fields = (
            'id', 'username', 'user_id', 'user_sec_id', 'follower_count', 'following_count',
            'follower_counter', 'is_active', 'last_activity', 'added_date', 'data'
        )
        self.select(data=data, **params)
        if self.is_available:
            self.set('data', loads(self.get('data')), onload=True)

    def insert(self):
        self._extend_defaults()
        super().insert()

    def _extend_defaults(self):
        defaults = {
            'id': 0,
            'username': '',
            'user_id': 0,
            'user_sec_id': '',
            'follow_count': 0,
            'following_count': 0,
            'follower_counter': 2000,
            'is_active': 1,
            'last_activity': datetime.now(),
            'added_date': datetime.now(),
            'data': {
                'followers_offset': 0,
                'total': 0,
                'error': 0,
                'max_time': 0,
                'min_time': 0,
            },
        }

        for field in self._fields:
            if self.get(field) == 0:
                continue
            if not self.get(field):
                self.set(field, defaults.get(field))

class DailySourcesModel(DataList):
    def __init__(self):
        super().__init__('daily_source', DailySourceModel, 'tiktok_users.db')
    
    def fetch_sources(self):
        # sql = '''
        # select * from daily_source where is_active = 1 and
        # (follower_counter > 0 or last_activity <= date('now', 'start of day'))
        # '''
        sql = '''
        select * from daily_source where is_active = 1 and
        (follower_counter > 0 or last_activity <= datetime('now', '-6 hours'))
        '''
        with Database(self._db_name) as db:
            db.execute(sql)

            results = []
            counter = 0
            for row in db.cursor:
                counter += 1
                results.append(self._Model(data=row))
                
                if counter == self._limit:
                    break
        return results
    


def add_source(username, Account, _type=None, no_proxy=False, proxy=None):
    try:
        user_id, sec_id = username_to_id(username)
    except Exception:
        logger.error('Error adding source. %s does not' %username)
        raise

    if not _type or _type == 'source':
        source = SourceModel(user_id=user_id)
    else:
        source = DailySourceModel(user_id=user_id)

    if source.is_available:
        logger.error('%s already exist' %username)
        return False

    if proxy:
        Account.set('proxy', proxy)
        no_proxy = False
    try:
        Tik = login(Account, no_proxy=no_proxy)
    except Exception:
        raise
    
    try:
        user_info = Tik.get_user_info(sec_id)
    except Exception:
        raise

    if user_info.user.is_private:
        logger.error('%s is private user' %username)
        return False
    
    (
        source.set('username', username)
        .set('user_id', user_id)
        .set('user_sec_id', sec_id)
        .set('follower_count', user_info.user.follower_count)
        .set('following_count', user_info.user.following_count)
        .save()
    )
    logger.info('%s successfully added' %username)
    
def add_sources(usernames, _type='daily'):
    ac = AccountModel(username='user8844751984164')

    if type(usernames) is not list:
        with open(usernames, encoding='UTF-8') as f:
            usernames = f.read().splitlines()

    if type(usernames) is not list and len(usernames) <= 0:
        raise TypeError('invalid argument')

    usernames = list(set(usernames))

    def helper(username):
        print('adding source: %s' %username.strip())
        try:
            add_source(username.strip(), ac, _type)
        except Exception as e:
            print('failed to add %s -> %s' %(username, e))

    while True:
        workers = min(5, len(usernames))
        print('usernames left: %s' %len(usernames))
        grabs = usernames[:workers]
        
        with futures.ThreadPoolExecutor(max_workers=workers) as executor:
            result = executor.map(helper, grabs)
            print(list(result))

        del usernames[:workers]
        if not usernames:
            break     


def scrapper(Account, source):
    if Account.get('login_required'):
        logger.error('%s. %s: login required' %(Account.get('id'), Account.get('username')))
        return False

    scraper_proxy = '104.131.89.39:50000'

    try:
        Tik = login(Account, proxy=scraper_proxy)
    except Exception as e:
        logger.error('%s. %s: Login Error -> %s' %(Account.get('id'), Account.get('username'), e))
        return False

    if source.get('data.followers_has_more'):
        logger.info('%s. %s: scrapping %s followers. offset: %s' %(
            Account.get('id'), Account.get('username'), source.get('username'), source.get('data.followers_offset'))
        )
        failed_counter = 0
        while True:
            try:
                Tik.proxy = scraper_proxy
                resp = Tik.get_followers(source.get('user_id'), source.get('user_sec_id'), source.get('data.min_time'))
            except tiktok.error.InvalidOperationException:
                logger.error('%s. %s failed to scrape followers of %s. Probably private account' %(
                    Account.get('id'), Account.get('username'), source.get('username')
                ))
                source.set('status', 2).save()
                source.set('last_activity', datetime.now()).save()
                return
            except tiktok.error.TikTokException:
                logger.error('%s. %s Error scrapping followers.. of %s' %(Account.get('id'), Account.get('username'),
                    source.get('username')))
                Account.set('data.error', Account.get('data.error') + 1).save()

                # if Account.get('data.error') % 3 == 0:
                #     set_new_proxy(Account)

                if Account.get('data.error') % 6 == 0:
                    try:
                        Tik._generate_device_v2()
                    except Exception:
                        logger.exception('%s. %s: Generating new device failed' %(Account.get('id'), Account.get('username')))
                    else:
                        logger.info('%s. %s: New device generated' %(Account.get('id'), Account.get('username')))
                        try:
                            Tik._send_login_flow(0)
                        except Exception as e:
                            logger.error('%s. %s: device login failed: %s' %(Account.get('id'), Account.get('username'), e))
                return False
            except (requests.exceptions.RequestException, requests.exceptions.ProxyError) as e:
                logger.error('%s: Scrapping %s requests error(%s): -> %s' %(
                    Account.get('username'), source.get('username'), scraper_proxy, e))
                failed_counter += 1
                # if '502' in str(e):
                #     set_new_proxy(Account)
                #     Tik = login(Account)

                if failed_counter >= 3:
                    # set_new_proxy(Account)
                    return False
            except Exception:
                logger.exception('%s. %s Error scrapping followers.. of %s' %(Account.get('id'), Account.get('username'),
                    source.get('username'))
                )
                return False
            else:
                if source.get('data.min_time') <= 0:
                    if resp.max_time <= source.get('data.max_time'):
                        logger.info('%s: %s no new followers' %(Account.get('username'), source.get('username')))
                        source.set('data.followers_has_more', 0)
                        source.set('data.max_time', 0)
                        source.set('data.min_time', 0)
                        source.set('last_activity', datetime.now()).save()
                        return
                    else:
                        source.set('data.temp_max_time', resp.max_time)

                if resp.max_time == -1 or resp.min_time == -1 or resp.min_time < source.get('data.max_time') or source.get('data.min_time') == resp.min_time:
                    logger.info('%s: %s no more followers' %(Account.get('username'), source.get('username')))
                    source.set('data.min_time', 0)
                    source.set('data.max_time', source.get('data.temp_max_time'))
                    source.set('last_activity', datetime.now()).save()
                    return

                source.set('data.min_time', resp.min_time)
                source.set('data.followers_offset', source.get('data.followers_offset') + 20)
                break
    elif source.get('data.followings_has_more'):
        logger.info('%s. %s: scrapping %s followings. offset: %s' %(
            Account.get('id'), Account.get('username'), source.get('username'), source.get('data.followings_offset'))
        )
        failed_counter = 0
        while True:
            try:
                Tik.proxy = scraper_proxy
                resp = Tik.get_followings(source.get('user_id'), source.get('user_sec_id'), source.get('data.max_time'))
            except tiktok.error.InvalidOperationException:
                logger.error('%s. %s failed to scrape followings of %s. Probably private account' %(
                    Account.get('id'), Account.get('username'), source.get('username')
                ))

                source.set('status', 2).save()
                source.set('last_activity', datetime.now()).save()
                return
            except tiktok.error.TikTokException:
                logger.error('%s. %s Error scrapping followings.. of %s' %(Account.get('id'), Account.get('username'),
                    source.get('username')))
                Account.set('data.error', Account.get('data.error') + 1).save()

                # if Account.get('data.error') % 3 == 0:
                #     set_new_proxy(Account)

                if Account.get('data.error') % 6 == 0:
                    try:
                        Tik._generate_device_v2()
                    except Exception:
                        logger.exception('%s. %s: Generating new device failed' %(Account.get('id'), Account.get('username')))
                    else:
                        logger.info('%s. %s: New device generated' %(Account.get('id'), Account.get('username')))
                        try:
                            Tik._send_login_flow(0)
                        except Exception as e:
                            logger.error('%s. %s: device login failed: %s' %(Account.get('id'), Account.get('username'), e))
                return False
            except (requests.exceptions.RequestException, requests.exceptions.ProxyError) as e:
                logger.error('%s: Scrapping %s requests error(%s): -> %s' %(
                    Account.get('username'), source.get('username'), scraper_proxy, e))
                failed_counter += 1
                # if '502' in str(e):
                #     set_new_proxy(Account)
                #     Tik = login(Account)

                if failed_counter >= 3:
                    # set_new_proxy(Account)
                    return False
            except Exception:
                logger.exception('%s. %s Error scrapping followings.. of %s' %(Account.get('id'), Account.get('username'),
                    source.get('username'))
                )
                return False
            else:
                if source.get('data.min_time') <= 0:
                    if resp.max_time <= source.get('data.max_time'):
                        logger.info('%s: %s no new followings' %(Account.get('username'), source.get('username')))
                        source.set('data.followings_has_more', 0)
                        source.set('data.max_time', 0)
                        source.set('data.min_time', 0)
                        source.set('status', 0)
                        source.set('last_activity', datetime.now()).save()
                        return
                    else:
                        source.set('data.temp_max_time', resp.max_time)

                if resp.max_time == -1 or resp.min_time == -1 or resp.min_time < source.get('data.max_time') or source.get('data.min_time') == resp.min_time:
                    logger.info('%s: %s no more followings' %(Account.get('username'), source.get('username')))
                    source.set('data.min_time', 0)
                    source.set('data.max_time', source.get('data.temp_max_time'))
                    source.set('last_activity', datetime.now()).save()
                    return

                source.set('data.min_time', resp.min_time)
                source.set('data.followings_offset', source.get('data.followings_offset') + 20)
                break
    else:
        logger.error('%s. %s: %s has no users to scrape consider resetting offsets' %(
            Account.get('id'), Account.get('username'), source.get('username'))
        )
        return

    if len(resp.users) <= 0:
        logger.info('%s. %s: %s returned empty users' %(Account.get('id'), Account.get('username'), source.get('username')))
        return

    results = []
    for user in resp.users:
        logger.debug('%s. %s: getting info of %s' %(Account.get('id'), Account.get('username'), user.username))
        failed_counter = 0
        while True:
            try:
                Tik.proxy = scraper_proxy
                user_info = Tik.get_user_info(sec_id=user.sec_id)
                if user_info.user.is_banned:
                    break
            except (requests.exceptions.RequestException, requests.exceptions.ProxyError) as e:
                logger.error('%s: Scrapping %s requests error(%s): -> %s' %(
                    Account.get('username'), source.get('username'), scraper_proxy, e))
                failed_counter += 1
                # if '502' in str(e):
                #     set_new_proxy(Account)
                #     Tik = login(Account)

                if failed_counter >= 3:
                    # set_new_proxy(Account)
                    return False
            except Exception as e:
                logger.error('%s: Error fetching info of %s: %s' %(Account.get('username'), user.username, e))
                results.append({
                    'username': user.username,
                    'user_id': user.user_id,
                    'user_sec_id': user.sec_id,
                    'follower_count': 0,
                    'following_count': 0,
                    'video_count': 1,
                    'bio': user.bio,
                    'language': '',
                    'is_private': int(user.is_private),
                    'last_activity': datetime.now(),
                    'added_date': datetime.now(),
                    'is_fetched': 0,
                    'comment_fetched': 0,
                    'status': 1,
                    'data': dumps({}),
                    'data2': dumps({
                        'followers_offset': 0,
                        'followers_has_more': 1,
                        'followings_offset' : 0,
                        'followings_has_more': 1,
                    })
                })
                break
            else:
                results.append({
                    'username': user_info.user.username,
                    'user_id': user_info.user.user_id,
                    'user_sec_id': user_info.user.sec_id,
                    'follower_count': user_info.user.follower_count,
                    'following_count': user_info.user.following_count,
                    'video_count': user_info.user.video_count,
                    'bio': user_info.user.bio,
                    'language': user_info.user.langauge,
                    'is_private': int(user_info.user.is_private),
                    'last_activity': datetime.now(),
                    'added_date': datetime.now(),
                    'is_fetched': 0,
                    'comment_fetched': 0,
                    'status': 1,
                    'data': dumps({}),
                    'data2': dumps({
                        'followers_offset': 0,
                        'followers_has_more': 1,
                        'followings_offset' : 0,
                        'followings_has_more': 1,
                    })
                })
                break

    # results = [
    #     user for user in results if  user['language'] in ('un', 'en', 'ca', 'it', 'de', 'fr', 'nl')]

    error_counter = 0
    while True:
        try:
            with Database('tiktok_users.db') as db:
                db.cursor.executemany('''
                    INSERT INTO users(username, user_id, user_sec_id, follower_count, following_count, video_count, bio, language, is_private, added_date, is_fetched, comment_fetched, data)
                    SELECT :username, :user_id, :user_sec_id, :follower_count, :following_count, :video_count, :bio, :language, :is_private, :added_date, :is_fetched, :comment_fetched, :data
                    WHERE NOT EXISTS (SELECT * FROM users WHERE user_id=:user_id)
                ''', results)
            break
        except OperationalError as e:
            logger.error('%s: users_table %s Counter: %s' %(Account.get('username'), e, error_counter))
            error_counter += 1
            if error_counter >= 50:
                raise
            time.sleep(randint(2, 3))
    
    source.set('last_activity', datetime.now()).save()
    logger.info('%s. %s: %s users added' %(Account.get('id'), Account.get('username'), len(results)))
    
    # add non private users to source table
    languages = ('en', 'ca', 'it', 'de', 'fr', 'nl', 'un')
    results = [user for user in results if not user['is_private'] and user['language'] in languages]

    error_counter = 0
    while True:
        try:
            with Database('tiktok_users.db') as db:
                db.cursor.executemany('''
                    INSERT INTO source(username, user_id, user_sec_id, follower_count, following_count, status, last_activity, added_date, data)
                    SELECT :username, :user_id, :user_sec_id, :follower_count, :following_count, :status, :last_activity, :added_date, :data2
                    WHERE NOT EXISTS (SELECT * FROM source WHERE user_id=:user_id)
                ''', results)
            break
        except OperationalError as e:
            logger.error('%s: source_table %s Counter: %s' %(Account.get('username'), e, error_counter))
            error_counter += 1
            if error_counter >= 50:
                raise
            time.sleep(randint(2, 3))

    logger.info('%s. %s: %s sources added' %(Account.get('id'), Account.get('username'), len(results)))

def daily_scrapper(Account, source, fetch_info=False):
    if Account.get('login_required'):
        logger.error('%s. %s: login required' %(Account.get('id'), Account.get('username')))
        return False

    # scraper_proxy = 'bodybad1:bodybad1@gate.dc.smartproxy.com:20000'
    scraper_proxy = '104.131.89.39:50000'

    try:
        Tik = login(Account, no_proxy=False, proxy=scraper_proxy)
    except Exception as e:
        logger.error('%s. %s: Login Error -> %s' %(Account.get('id'), Account.get('username'), e))
        return False

    # check for new followers, since last time
    failed_counter = 0
    if source.get('follower_counter') <= 0:
        while True:
            try:
                Tik.proxy = scraper_proxy
                resp = Tik.get_user_info(source.get('user_sec_id'))
                break
            except tiktok.error.UserNotExit as e:
                logger.exception('%s Error: %s' %(Account.get('username'), e))
                source.set('is_active', 2).save()
                return
            except tiktok.error.TikTokException as e:
                logger.error('%s Error fetching source info %s: %s' %(Account.get('username'),
                    source.get('username'), e)
                )

                # Account.set('data.error', Account.get('data.error') + 1).save()

                # if Account.get('data.error') % 3 == 0:
                #     set_new_proxy(Account)

                # if Account.get('data.error') % 6 == 0:
                #     try:
                #         Tik._generate_device_v2()
                #     except Exception:
                #         logger.exception('%s. %s: Generating new device failed' %(Account.get('id'), Account.get('username')))
                #     else:
                #         logger.info('%s. %s: New device generated' %(Account.get('id'), Account.get('username')))
                #         try:
                #             Tik._send_login_flow(0)
                #         except Exception as e:
                #             logger.error('%s. %s: device login failed: %s' %(Account.get('id'), Account.get('username'), e))
                return False
            except (requests.exceptions.RequestException, requests.exceptions.ProxyError) as e:
                logger.error('%s: fetching source info %s requests error(%s): -> %s' %(
                    Account.get('username'), source.get('username'), scraper_proxy, e))
                failed_counter += 1
                if failed_counter >= 3:
                    return False
                # if '502' in str(e):
                #     set_new_proxy(Account)
                #     Tik=login(Account)
            except Exception:
                logger.error('source info')
                return False

        counter = resp.user.follower_count - source.get('follower_count')
        if counter > 0:
            source.set('follower_count', resp.user.follower_count)
            source.set('follower_counter', counter)
        else:
            logger.info('%s: %s no new followers since last time' %(Account.get('username'), source.get('username')))
            # source.set('last_activity', datetime.now()).save()
        
    # max_time = int(time.time()) - 60*60
    logger.info('%s: scrapping %s followers. offset: %s. Counter: %s' %(
        Account.get('username'), source.get('username'), source.get('data.followers_offset'),
        source.get('follower_counter'))
    )
    
    failed_counter = 0
    while True:
        try:
            Tik.proxy = scraper_proxy
            resp = Tik.get_followers(
                source.get('user_id'), source.get('user_sec_id'), source.get('data.min_time'), source_type=1)
        except tiktok.error.InvalidOperationException as e:
            logger.error('%s: failed to scrape followers of %s. Probably private account -> %s' %(
                Account.get('username'), source.get('username'), e)
            )
            source.set('is_active', 3).set('last_activity', datetime.now()).save()
            return
        except tiktok.error.TikTokException as e:
            logger.error('%s Error scrapping followers of %s: %s' %(Account.get('username'),
                source.get('username'), e)
            )
            # Account.set('data.error', Account.get('data.error') + 1).save()

            # if Account.get('data.error') % 6 == 0:
            #     try:
            #         Tik._generate_device_v2()
            #     except Exception:
            #         logger.exception('%s. %s: Generating new device failed' %(Account.get('id'), Account.get('username')))
            #     else:
            #         logger.info('%s. %s: New device generated' %(Account.get('id'), Account.get('username')))
            #         try:
            #             Tik._send_login_flow(0)
            #         except Exception as e:
            #             logger.error('%s. %s: device login failed: %s' %(Account.get('id'), Account.get('username'), e))
            return False
        except tiktok.error.AccountDisabledException:
            logger.exception('%s. %s: Account disabled' %(Account.get('id'), Account.get('username')))
            Account.set('login_required', 2).save()
            return False
        except (requests.exceptions.RequestException, requests.exceptions.ProxyError) as e:
            logger.error('%s: Scrapping %s requests error(%s): -> %s' %(
                Account.get('username'), source.get('username'), scraper_proxy, e))
            failed_counter += 1
            if failed_counter >= 3:
                return False

            # if '502' in str(e):
            #     set_new_proxy(Account)
            #     Tik = login(Account)
        except Exception:
            logger.exception('%s Error scrapping followers.. of %s' %(Account.get('username'),
                source.get('username'))
            )
            return False
        else:
            if source.get('data.min_time') <= 0:
                if resp.max_time <= source.get('data.max_time'):
                    logger.info('%s: %s no new followers' %(Account.get('username'), source.get('username')))
                    source.set('last_activity', datetime.now()).save()
                    return
                else:
                    source.set('data.temp_max_time', resp.max_time)
                    if source.get('follower_counter') <= 0:
                        source.set('follower_counter', 2000)

            if resp.max_time == -1 or resp.min_time == -1 or resp.min_time < source.get('data.max_time') or source.get('data.min_time') == resp.min_time:
                logger.info('%s: %s no more followers' %(Account.get('username'), source.get('username')))
                source.set('follower_counter', 0)
                source.set('data.min_time', 0)
                source.set('data.max_time', source.get('data.temp_max_time'))
                source.set('data.followers_offset', 0)
                source.set('last_activity', datetime.now()).save()
                return
            source.set('data.min_time', resp.min_time)
            break
   
    if not resp.users:
        logger.error('%s: %s returned empty users' %(Account.get('username'), source.get('username')))

        # if source.get('last_activity').day != datetime.now().day:
        #     source.set('data.error', 1)
        # else:
        #     source.set('data.error', source.get('data.error') + 1)
        
        # if source.get('data.error') >= 5:
        #     source.set('is_active', 2)

        # source.set('last_action_date', datetime.now()).save()
        # source.save()
        return
    
    results = []
    for user in resp.users:
        logger.debug('%s. %s: getting info of %s' %(Account.get('id'), Account.get('username'), user.username))
        try:
            if not fetch_info:
                raise Exception

            user_info = Tik.get_user_info(sec_id=user.sec_id)
            if user_info.user.is_banned:
                continue
        except Exception as e:
            if fetch_info:
                logger.error('%s: Error fetching info of %s: %s' %(Account.get('username'), user.username, e))

            results.append({
                'username': user.username,
                'user_id': user.user_id,
                'user_sec_id': user.sec_id,
                'follower_count': 0,
                'following_count': 0,
                'video_count': 1,
                'bio': user.bio,
                'language': '',
                'is_private': int(user.is_private),
                'last_activity': datetime.now(),
                'added_date': datetime.now(),
                'is_fetched': 0,
                'comment_fetched': 0,
                'status': 1,
                'data': dumps({}),
                'data2': dumps({
                    'followers_offset': 0,
                    'followers_has_more': 1,
                    'followings_offset' : 0,
                    'followings_has_more': 1,
                })
            })
        else:
            results.append({
                'username': user_info.user.username,
                'user_id': user_info.user.user_id,
                'user_sec_id': user_info.user.sec_id,
                'follower_count': user_info.user.follower_count,
                'following_count': user_info.user.following_count,
                'video_count': user_info.user.video_count,
                'bio': user_info.user.bio,
                'language': user_info.user.langauge,
                'is_private': int(user_info.user.is_private),
                'last_activity': datetime.now(),
                'added_date': datetime.now(),
                'is_fetched': 0,
                'comment_fetched': 0,
                'status': 1,
                'data': dumps({}),
                'data2': dumps({
                    'followers_offset': 0,
                    'followers_has_more': 1,
                    'followings_offset' : 0,
                    'followings_has_more': 1,
                })
            })
        time.sleep(randint(1, 2))

    # select users with this lang
    # results = [
    #     user for user in results if  user['language'] in ('en', 'ca', 'it', 'de', 'fr', 'nl')]

    error_counter = 0
    while True:
        try:
            with Database('tiktok_users.db') as db:
                db.cursor.executemany('''
                    INSERT INTO users(username, user_id, user_sec_id, follower_count, following_count, video_count, bio, language, is_private, added_date, is_fetched, comment_fetched, data)
                    SELECT :username, :user_id, :user_sec_id, :follower_count, :following_count, :video_count, :bio, :language, :is_private, :added_date, :is_fetched, :comment_fetched, :data
                    WHERE NOT EXISTS (SELECT * FROM users WHERE user_id=:user_id)
                ''', results)
            break
        except OperationalError as e:
            logger.error('%s: users_table %s Counter: %s' %(Account.get('username'), e, error_counter))
            error_counter += 1
            if error_counter >= 50:
                raise
            time.sleep(randint(2, 3))

    # source.set('follower_counter', source.get('follower_counter') - 20)
    source.set('data.followers_offset', source.get('data.followers_offset') + 20)
    source.set('data.total', source.get('data.total') + 20)
    source.set('last_activity', datetime.now()).save()
    logger.info('%s: %s users added' %(Account.get('username'), len(results)))
    
    # add non private users to source table
    # results = [user for user in results if not user['is_private']]
    # error_counter = 0
    # while True:
    #     try:
    #         with Database('tiktok_users.db') as db:
    #             db.cursor.executemany('''
    #                 INSERT INTO source(username, user_id, user_sec_id, follower_count, following_count, status, last_activity, added_date, data)
    #                 SELECT :username, :user_id, :user_sec_id, :follower_count, :following_count, :status, :last_activity, :added_date, :data2
    #                 WHERE NOT EXISTS (SELECT * FROM source WHERE user_id=:user_id)
    #             ''', results)
    #         break
    #     except OperationalError as e:
    #         logger.error('%s: source_table %s Counter: %s' %(Account.get('username'), e, error_counter))
    #         error_counter += 1
    #         if error_counter >= 50:
    #             raise
    #         time.sleep(randint(2, 3))

    # logger.info('%s: %s sources added' %(Account.get('username'), len(results)))

def scrape_followings(username, info=False):
    ac = AccountModel(username='user006001128')
    Tik = login(ac, no_proxy=True)
    user_id, user_sec_id = username_to_id(username)
    max_time = 0
    offset = 0
    print('scapping followings of %s' % username)
    source_info = Tik.get_user_info(user_sec_id)
    print('Followings Count: %s' % source_info.user.following_count)

    results = 'username,followers,followings,link\n'
    while True:
        print('offset: %s' % offset)
        resp = Tik.get_followings(
            user_id,
            user_sec_id, 
            max_time, 
            offset
        )
        if not resp.users:
            print('empty resp')
            break

        for user in resp.users:
            if info:
                user = Tik.get_user_info(user.sec_id).user
    
            results += '{},{},{},https://www.tiktok.com/@{}\n'.format(
                user.username,
                user.follower_count,
                user.following_count,
                user.username
            )
        max_time = resp.max_time
        offset = resp.offset
    
        if offset >= 2000 or not resp.has_more or abs(source_info.user.following_count - offset) <= 10:
            break
        # time.sleep(3)
    
    with open(f'sources/{username}Followings.csv', 'w') as f:
        f.write(results)
    
    print('done')


def scrapper_wrapper(args):
    return scrapper(*args)

def daily_scrapper_wrapper(args):
    return daily_scrapper(*args)


def func_wrapper(args):
    func, arg1, arg2 = args
    return func(arg1, arg2)

def scrapper_worker(stop_e):
    logger.info('scrapper_worker started')
    error_counter = 0
    workers = 4
    executor = futures.ThreadPoolExecutor(workers)

    while not stop_e.is_set():
        # fetch dedicated scrape accounts
        accounts = (
            AccountsModel()
            .where('tags', 'like', f'%scrape1%')
            .where('login_required', '=', 0)
            .order_by('last_login', 'ASC')
            .limit(workers)
            .fetch_data()
        )

        # remain = workers - len(accounts)
        # if remain:
        #     t = time_int(datetime.now())
        #     if t >= 1200:
        #         query = AccountsModel().where('tags', 'like', f'%001%')
        #     else:
        #         query = AccountsModel().where('tags', 'like', f'%002%')
        #     accounts.extend(query.where('login_required', '=', 0).limit(remain).fetch_data())

        if not accounts:
            logger.error('No scrapper_worker account active. stopping')
            break
            
        functions = []
        sources = []
        daily_sources = DailySourcesModel().limit(len(accounts)).fetch_sources()
        for _ in daily_sources:
            functions.append(daily_scrapper)

        # remain = len(accounts) - len(daily_sources)
        # if remain > 0:
        #     logger.error('%s daily sources found' %len(daily_sources))
        #     sources = (
        #         SourcesModel()
        #         .where('status', '=', '1')
        #         .limit(remain)
        #         .fetch_data()
        #     )
        #     for s in sources:
        #         if s.get('data.min_time') == None:
        #             s.set('data.min_time', 0)
        #             s.set('data.max_time', 0)
        #             s.set('data.followers_offset', 0)
        #             s.set('data.followings_offset', 0)
        #             s.set('data.followers_has_more', 1)
        #             s.set('data.followings_has_more', 1).save()
        #         functions.append(scrapper)

        sources = daily_sources + sources
        if not sources:
            logger.error('No sources to scrape, consider adding adding sources or reset offsets. Sleeping for 20 mins')
            time.sleep(20*60)
            continue

        results = executor.map(func_wrapper, zip(functions, accounts, sources))
        results = list(results)

        logger.debug(
            'Accounts: %s Results: %s'
            %([acc.get('username') for acc in accounts], results)
        )

        # count number of False. False means unscuccessfull operation
        error_counter = reduce(lambda counter, result: counter + 1 if result == False else counter, results, error_counter)

        # stop if too many False
        if error_counter >= 5:
            # instead of exiting sleep for 25mins 
            logger.error('Sleeeping scrapper worker for 5 mins, too many errors: %s' %error_counter)
            error_counter = 0
            time.sleep(5*60)
        
        # break
        accounts.clear()
        sources.clear()
        time.sleep(randint(2, 5))
    executor.shutdown(True)
    logger.info('Exiting scrapper_worker')


def start_db(new_db_name, old_db_name='tiktok_users.db', **tables):
    with Database(new_db_name) as db:
	    db.create_tables('db/tiktok_users_schema.sql')
    
    def update(table):
        if table == 'daily':
            sql = 'select * from daily_source'
        elif table == 'source':
            sql = 'select * from source'
        elif table == 'users':
            sql = 'select * from users where is_fetched=0'
        else:
            raise TypeError('Incorrect table name')
        
        print('table name: %s' %table)
        # select from old db
        error_counter = 0
        while True:
            try:
                with Database(old_db_name) as db:
                    db.execute(sql)
                    data = db.fetchall()
                break
            except OperationalError as e:
                error_counter += 1
                print('%s. %s' %(error_counter, e))
                if error_counter >= 5:
                    raise
                time.sleep(randint(2, 3))
        # get rid of row id
        data = [source[1:] for source in data]
        if not data:
            print('%s is empty' %table)
            return

        # print('%s: %s data selected' %(len(data), table))

        # insert into new db
        if table == 'daily':
            sql = 'INSERT INTO daily_source(username, user_id, user_sec_id, follower_count, \
                following_count, follower_counter, is_active, last_activity, added_date, data) \
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
        elif table == 'source':
            sql = 'INSERT INTO source(username, user_id, user_sec_id, follower_count, \
                following_count, status, last_activity, added_date, data) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)'
        elif table == 'users':
            sql = 'INSERT INTO users(username, user_id, user_sec_id, follower_count, following_count, video_count, bio, \
                language, is_private, added_date, is_fetched, comment_fetched, data) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'

        error_counter = 0
        while True:
            try:
                with Database(new_db_name) as db:
                    db.cursor.executemany(sql, data)
                break
            except OperationalError as e:
                print('%s. %s' %(error_counter, e))
                error_counter += 1
                if error_counter >= 5:
                    raise
                time.sleep(randint(2, 3))
            
        print('%s data inserted in %s' %(len(data), table))

    daily = tables.get('daily', True)
    source = tables.get('source', True)
    users = tables.get('users', True)

    if daily:
        update('daily')
    
    if source:
        update('source')
    
    if users:
        update('users')
        
if __name__ == "__main__":
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.CRITICAL)
    setup_logger('scrape_root.log', root_logger, True)

    stop_e = threading.Event()
    t1 = threading.Thread(target=scrapper_worker, args=(stop_e,))
    t1.start()