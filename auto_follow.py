import logging
import random
import time
from datetime import datetime, timedelta
from requests.exceptions import RequestException, ProxyError

from tiktok.tiktok import TikTok
from tiktok.utils import generate_random, username_to_id
import tiktok.error

from models import Database, AccountModel, FollowScheduleModel, UnFollowScheduleModel, FollowLogModel, FollowLogsModel, DeviceModel
from utils import login, _login, setup_logger, device_manager, proxy_error, set_new_proxy

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
setup_logger('auto_follow.log', logger)


def scrape_users(Account, sc, Tik):
    # get active target:
    active_targets = {
        k:v['source'] for k, v in sc.get('target').items() if v['status']
    }

    # randomly choose target from the active targets.
    while True:
        if len(active_targets) == 0:
            logger.error(
                '%s. %s: No active target / source set to scrape. auto-follow disabled' %(Account.get('id'), Account.get('username')))
            sc.disable()
            return False

        if 'users' in active_targets:
            target = 'users'
        else:
            target, sources = random.choice(list(active_targets.items()))
            if len(sources) == 0:
                del active_targets[target]
                logger.error('%s. %s: auto-follow %s target has empty source!!' %(Account.get('id'), Account.get('username'), target))
                continue

        # target can have more than one source. randomly select source from target.
        if target == 'followers' or target == 'followings':
            '''scrape followers/followings'''
            idx = random.randrange(len(sources))
            source = sources[idx]
            logger.info('%s. %s: scrapping %s follower/followings ' %(Account.get('id'), Account.get('username'), source[0]))

            if type(source) is list and len(source) == 5:
                pass
            elif type(source) is list and len(source) == 3:
                source.extend([0, 0])
            else:
                logger.error('%s. %s: %s source format is wrong. deleting' % (Account.get('id'), Account.get('username'), source))
                del sources[idx]
                sc.set('target', sc.get('target')).save()
                continue

            # Device ban or bad proxy which will let request return empty response.
            # exception is throw when that happens
            if target == 'followers':
                try:
                    resp = Tik.get_followers(
                        source[1], source[2], source[3], source[4]
                    )
                except Exception:
                    logger.exception('%s. %s: error scrappig followers of source: %s' % (
                        Account.get('id'), Account.get('username'), source))
                    break
            else:
                try:
                    resp = Tik.get_followings(
                        source[1], source[2], source[3], source[4]
                    )
                except Exception:
                    logger.exception('%s. %s: error scrappig followings of source: %s' % (
                        Account.get('id'), Account.get('username'), source))
                    break

            if len(resp.users) < 1:
                # This is not supposed to happen unless source really have empty followers/followings.
                # or maybe is private??
                # TODO:
                    # check if source is not set to private
                msg = '%s. %s: %s source returned empty %s!!.'
                logger.error(msg % (Account.get('id'), Account.get('username'), source, target))
                continue

            source[3] = resp.max_time
            source[4] = resp.offset if resp.offset < 2000 else 0
            sc.get('data')['users'].extend(
                [[user.username, user.user_id, user.sec_id] for user in resp.users])
            sc.get('data')['target'] = {
                'type': target, 'user': source[0], 'user_id': source[1], 'sec_id': source[2]
            }
            if not resp.has_more:
                logger.error('%s. %s: %s has no more %s!!.' %(Account.get('id'), Account.get('username'), source, target))
                source[3] = 0
                source[4] = 0

            sc.set('target', sc.get('target')).save()  # trigger save
            break
        if target == 'comments':
            '''scrape commenters'''
            source = random.choice(sources)
            raise NotImplementedError
        if target == 'users':
            # already scraped users, just grab add some to cache
            logger.debug('%s. %s: source -> users' %(Account.get('id'), Account.get('username')))

            users = sc.fetch_users(100)
            if not users:
                logger.error('%s. %s: empty user sources' %(Account.get('id'), Account.get('username')))
                del active_targets[target]
                continue

            sc.set('data.users', users)
            sc.set('data.target', {
                'type': target,
            })
            sc.set('data', sc.get('data')).save()
            break


def auto_follow(Account, sc, stop_e=None):
    '''
    Account: AccountModel
    sc: FollowScheduleModel
    stop_e: thread.Event
    '''
    if Account.get('login_required') or not sc.get('is_active') or datetime.now() < sc.get('schedule_date'):
        msg = '%s. %s: Auto follow failed to run. Either login required or schedule not active or due'
        logger.error(msg % (Account.get('id'), Account.get('username')))
        return False

    followed_today = (
        FollowLogsModel()
        .where('account_id', '=', Account.get('id'))
        .where('status', '=', 'success')
        .where('followed_date', '>=', 'date', 'now', 'start of day')
        .count()
    )
    if followed_today >= sc.get('settings.max_per_day'):
        logger.info('%s. %s: max follow per day reached. Schedule follow to next day' %(Account.get('id'), Account.get('username')))
        next_day = (datetime.now() + timedelta(days=1)
                    ).replace(hour=0, minute=0, second=0, microsecond=0)
        next_time = random.randint(20, 40)
        sc.set('schedule_date', next_day + timedelta(minutes=next_time)).save()
        return False

    max_to_follow = random.randint(
        sc.get('settings.follows_per_op_min'), sc.get('settings.follows_per_op_max'))

    try:
        Tik = login(Account)
        # Tik = _login(Account)
    except Exception:
        logger.error('%s. %s login failed' %(Account.get('id'), Account.get('username')))
        return False

    error_counter = 0
    while stop_e and not stop_e.is_set() and not sc.is_disabled:
        if len(sc.get('data')['users']) == 0:
            '''no users in cache let's randomly choose a source from active target 
            and scrape or fetch users and put in cache(data field). targets: (followers, followings
            users: scrape from somewhere else)'''
            logger.info('%s. %s: No cached users. Trying to scrape' %(Account.get('id'), Account.get('username')))
            scrape_users(Account, sc, Tik)

            # if we aint get any users to follow shedule and return
            if len(sc.get('data')['users']) == 0:
                logger.info('%s. %s: No users to follow. Follow re-scheduled' %(
                    Account.get('id'), Account.get('username')))
                next_time = random.randint(
                    sc.get('settings.next_op_min'), sc.get('settings.next_op_max'))
                sc.set('schedule_date', datetime.now() +
                       timedelta(minutes=next_time)).save()
                return False

        # trigger save. a stupid hack that needs addressing
        sc.set('data', sc.get('data'))

        username = user_id = user_sec_id = None
        user = sc.get('data')['users'][0]  # get user from cache

        if len(user) == 3:
            username, user_id, user_sec_id = user
        elif type(user) == str or len(user) == 1:
            username = user if type(user) is str else user[0]
            try:
                user_id, user_sec_id = username_to_id(username)
            except ValueError:
                # if username_to_id failed to find user
                logger.exception('%s. %s: ValueError' % (Account.get('id'), Account.get('username')))
                del sc.get('data')['users'][0]
                continue
            except Exception:
                # requests error. interet down??
                next_time = random.randint(
                    sc.get('settings.next_op_min'), sc.get('settings.next_op_max'))
                logger.exception('%s. %s: Error. Will run again in %s minutes' % (Account.get('id'),
                    Account.get('username'), next_time))

                # we don't want to crash forever. do we?. r-reschedule
                sc.set('schedule_date', datetime.now() +
                       timedelta(minutes=next_time)).save()
                return False
        else:
            # invalid user format
            logger.error('%s. %s: %s format is invalid. deleting' %
                         (Account.get('id'), Account.get('username'), user))
            del sc.get('data')['users'][0]
            continue

        if sc.get('filters.unique_accross'):
            Log = FollowLogModel(user_id=user_id)
        else:
            Log = FollowLogModel(account_id=Account.get('id'), user_id=user_id)

        if Log.is_available and Log.get('status') in ('success', 'unfollowed'):
            del sc.get('data')['users'][0]
            logger.debug('%s. %s: %s already followed' %
                (Account.get('id'), Account.get('username'), username))
            continue

        # get user info
        # try:
        #     Tik.proxy = 'bodybad1:bodybad1@gate.dc.smartproxy.com:20000'
        #     user_info = Tik.get_user_info_v2(user_id, user_sec_id)
        #     if user_info.user.is_banned:
        #         del sc.get('data')['users'][0]
        #         logger.error('%s. %s: %s banned' %(Account.get('id'), Account.get('username'), username))
        #         continue
        # except (tiktok.error.UserNotExit, tiktok.error.CantFollowUserException) as e:
        #     del sc.get('data')['users'][0]
        #     logger.error('%s. %s: %s %s' %(Account.get('id'), Account.get('username'), username, e))
        #     continue
        # except (RequestException, ProxyError) as e:
        #     error_counter += 1
        #     logger.error('%s. %s: getting user info error (%s): %s %s' %(Account.get('id'), 
        #         Account.get('username'), error_counter, Account.get('proxy'), e))
            
        #     if '502' in str(e):
        #         set_new_proxy(Account)
        #         Tik = login(Account)
            
        #     if error_counter >= 3:
        #         sc.save()
        #         set_new_proxy(Account)
        #         return False
        #     time.sleep(random.randint(3, 5))
        #     continue
        # except tiktok.error.TikTokException as e:
        #     # Account.set('data.error', Account.get('data.error') + 1).save()
        #     logger.error('%s. %s: getting user info error: %s' %(Account.get('id'),
        #         Account.get('username'), e))
        # except Exception:
        #     del sc.get('data')['users'][0]
        #     logger.exception('%s. %s:' %(Account.get('id'), Account.get('username')))
        #     continue
        # else:
        #     error_counter = 0  
        
        (
            Log.set('account_id', Account.get('id'))
            .set('user_id', user_id)
            .set('user_sec_id', user_sec_id)
            .set('data', {
                'followed': {
                    'username': username},
                'target': sc.get('data')['target']})
        )

        failed_counter = 0
        while True:
            try:
                Tik.proxy = Account.get('proxy')
                Tik.follow_by_id(user_id, user_sec_id)
            except tiktok.error.TooMuchRequestException:
                msg = '%s. %s:Error. Will run again in %s hours %s minutes'
                # schedule to 12 hours from now
                # if it slip to next day. start at 00:00 of next day
                # restriction always seems to be lifted after 12hrs or next day GMT
                now = datetime.now()
                next_time =  now + timedelta(hours=12)
                if next_time.day > now.day:
                    next_time = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

                rand_mins = random.randint(15, 35)
                sc.set('schedule_date', next_time + timedelta(minutes=rand_mins)).save()

                secs = (now - sc.get('schedule_date')).total_seconds()
                logger.exception(msg %(Account.get('id'), Account.get('username'),
                    int(secs // 3600), (secs % 3600) // 60)
                )
                return False
            except tiktok.error.FollowFailedException:
                Account = AccountModel(id=Account.get('id'))
                Account.set('last_action_date', datetime.now())
                Account.set('data.follow_failed', Account.get('data.follow_failed') + 1).save()

                if Account.get('data.follow_failed') % 5 == 0:
                    next_time = random.randint(360, 400)
                    set_new_proxy(Account)
                    try:
                        Tik=login(Account, force_login_flow=True)
                    except Exception:
                        pass
                else:
                    next_time = random.randint(25, 45)
                
                del sc.get('data')['users'][0]
                    
                # if Account.get('data.follow_failed') >= 10:
                #     tags = Account.get('tags')
                #     tags = tags + ', F_STOP' if tags else 'F_STOP'
                #     Account.set('tags', tags).save()
                #     sc.disable()

                msg = '%s. %s: Failed to follow %s. auto-follow will run again %s mins from now'
                logger.error(msg %(Account.get('id'), Account.get('username'), username, next_time))
                sc.set('schedule_date', datetime.now() + timedelta(minutes=next_time)).save()
                return False
            except (tiktok.error.CantFollowUserException, tiktok.error.ServerError, tiktok.error.UserNotExit) as e:
                logger.error('%s. %s: Error. bad user %s: %s' %(Account.get('id'), Account.get('username'), username, e))
                Log.save()
                del sc.get('data')['users'][0]
                break
            except tiktok.error.FollowLimitReached as e:
                logger.error('%s. %s: Follow limit reached: %s. Enable unfollow' %(Account.get('id'), Account.get('username'), e))
                sc.disable()

                # enable unfollow
                UnFollowScheduleModel(account_id=sc.get('account_id')).enable()
                return False
            # except tiktok.error.TikTokException:
            #     logger.exception('%s. %s: Error. Will continue' %(Account.get('id'), Account.get('username')))
            #     time.sleep(1)
            #     continue
            except (RequestException, ProxyError) as e:
                logger.error('%s. %s: Failed to follow. %s Requests error: -> %s' %(
                    Account.get('id'), Account.get('username'), Account.get('proxy'), e))

                failed_counter += 1
                if failed_counter >= 3:
                    sc.save()
                    return False
                
                set_new_proxy(Account)
                Tik = login(Account, force_login_flow=True)

                # next_time = random.randint(sc.get('settings.next_op_min'), sc.get('settings.next_op_max'))
                # sc.set('schedule_date', datetime.now() + timedelta(minutes=next_time)).save()

                # Account.set('data.proxy_error', Account.get('data.proxy_error') + 1).save()
                # proxy_error(Account.get('proxy'))
                continue
            except tiktok.error.AccountDisabledException:
                logger.exception('%s. %s: Account disabled' %(Account.get('id'), Account.get('username')))
                Account.set('login_required', 2).save()
                sc.save()
                raise
                # return False
            except tiktok.error.LoginExpiredException as e:
                if str(e).lower() == 'invalid parameters':
                    del sc.get('data')['users'][0]
                    break
                logger.error('%s. %s: %s' %(Account.get('id'), Account.get('username'), e))
                Account.set('login_required', 1).save()
                sc.save()
                raise
                # return False
            except Exception as e:
                # internet problem??, i'm catching all execeptions and logging
                # what could go wrong. will improve the later
                if isinstance(e, tiktok.error.TikTokException):
                    del sc.get('data')['users'][0]
                    
                next_time = random.randint(2, 5)
                logger.exception('%s. %s: Follow Error. Will run again in %s minutes' % (Account.get('id'),
                    Account.get('username'), next_time))

                # we don't want to crash forever. do we?. r-reschedule
                sc.set('schedule_date', datetime.now() +
                    timedelta(minutes=next_time)).save()
                # Log.save()
                return False
            else:
                logger.info('%s. %s: %s successfully followed' %(Account.get('id'), Account.get('username'), username))

                # get user info
                try:
                    Tik.get_user_info_v2(user_id, user_sec_id)
                except Exception:
                    pass

                del sc.get('data')['users'][0]
                Log.set('status', 'success').save()
                max_to_follow -= 1
                followed_today += 1
                Account = AccountModel(id=Account.get('id'))
                Account.set('data.follow_failed', 0).save()
                break

        if max_to_follow <= 0:
            break

        time.sleep(random.randint(sc.get('settings.sleep_min'), sc.get('settings.sleep_max')))

    logger.info('%s. %s: %s followed today' %
        (Account.get('id'), Account.get('username'), followed_today))
    next_time = random.randint(
        sc.get('settings.next_op_min'), sc.get('settings.next_op_max'))
    sc.set('schedule_date', datetime.now() +
           timedelta(minutes=next_time)).save()
    return True
