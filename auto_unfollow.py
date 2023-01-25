import logging
import random
import time
from datetime import datetime, timedelta
from requests.exceptions import RequestException, ProxyError

from tiktok.tiktok import TikTok
import tiktok.error

from models import (
    AccountModel, UnFollowScheduleModel, UnFollowLogModel, UnFollowLogsModel, 
    FollowLogModel, FollowLogsModel, FollowScheduleModel)
from utils import login, _login, setup_logger, proxy_error

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
setup_logger('auto_unfollow.log', logger)


def auto_unfollow(Account, sc, stop_e=None):
    '''
    Account: AccountModel
    sc: unFollowScheduleModel
    stop_e: thread.Event
    '''
    if Account.get('login_required') or not sc.get('is_active') or datetime.now() < sc.get('schedule_date'):
        msg = '%s. %s: Auto follow failed to run. Either login required or schedule not active or due'
        logger.error(msg % (Account.get('id'), Account.get('username')))
        return False

    unfollowed_today = (
        UnFollowLogsModel()
        .where('account_id', '=', Account.get('id'))
        .where('status', '=', 'success')
        .where('unfollowed_date', '>=', 'date', 'now', 'start of day')
        .count()
    )
    if unfollowed_today >= sc.get('settings.max_per_day'):
        logger.info('%s. %s: max unfollow per day reached. Schedule unfollow to next day' %(
            Account.get('id'), Account.get('username')))
        next_day = (datetime.now() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        next_time = random.randint(
            sc.get('settings.next_op_min'), sc.get('settings.next_op_max'))
        sc.set('schedule_date', next_day + timedelta(minutes=next_time)).save()
        return False

    try:
        Tik = login(Account, no_proxy=True)
    except Exception as e:
        logger.error('%s. %s: failed to login: %s' %(Account.get('id'), Account.get('username'), e))
        return False
    
    if sc.get('data.following_count') <= sc.get('settings.stop_at'):
        try:
            resp = Tik.get_self_info()
        except (RequestException, ProxyError) as e:
            proxy = Account.get('proxy')
            logger.error('%s. %s: Failed to get self info. %s Network Error -> %s' %(
                Account.get('id'), Account.get('username'), proxy, e))
            return False
        except Exception:
            logger.exception('%s. %s Error' %(Account.get('id'), Account.get('username')))
            return False
        else:
            sc.set('data.following_count', resp.user.following_count).save()
            if sc.get('data.following_count') <= sc.get('settings.stop_at'):
                logger.info('%s. %s: . unfollow disabled. Followings: %s' %(
                    Account.get('id'), Account.get('username'), sc.get('data.following_count')))
                sc.disable()
                FollowScheduleModel(account_id=sc.get('account_id')).enable()
                return False

    max_to_unfollow = random.randint(
        sc.get('settings.unfollows_per_op_min'), sc.get('settings.unfollows_per_op_max'))

    while stop_e and not stop_e.is_set() and not sc.is_disabled:
        # try:
        #     resp = Tik.get_self_followings(sc.get('data.max_time'), sc.get('data.offset'))
        #     sc.set('data.max_time', resp.min_time)
        # except (RequestException, ProxyError) as e:
        #     proxy = Account.get('proxy')
        #     logger.error('%s. %s: Failed to scrape followings. %s Requests Error: %s' %(
        #         Account.get('id'), Account.get('username'), proxy, e))
        #     # Account.set('data.proxy_error', Account.get('data.proxy_error') + 1).save()
        #     proxy_error(proxy)
        #     return False
        # except Exception:
        #     logger.exception('%s. %s Error scrapping followings' %(Account.get('id'), Account.get('username')))
        #     return False

        # if not resp.users:
        #     logger.info('%s. %s: returned empty followings' %(Account.get('id'), Account.get('username')))
        #     if sc.get('data.following_count') <= sc.get('settings.stop_at'):
        #         sc.disable()
        #         logger.info('%s. %s: . unfollow disabled. Followings: %s' %(
        #             Account.get('id'), Account.get('username'), resp.user.following_count))
        #     break
        
        followed_logs = (
            FollowLogsModel()
            .where('account_id', '=', Account.get('id'))
            .where('status', '=', 'success').
            limit(max_to_unfollow).
            fetch_data()
        )
        if not followed_logs:
            logger.info('%s. %s: returned empty followed logs' %(Account.get('id'), Account.get('username')))
            # if sc.get('data.following_count') <= 1000 or sc.get('data.following_count') <= sc.get('settings.stop_at'):
            sc.disable()
            FollowScheduleModel(account_id=sc.get('account_id')).enable()
            logger.info('%s. %s: . unfollow disabled. Followings: %s' %(
                Account.get('id'), Account.get('username'), sc.get('data.following_count')))
            break

        for log in followed_logs:
            try:
                log_username = log.get('data').get('followed').get('username')
            except Exception:
                log_username = ''
            try:
                Tik.proxy = ''
                resp = Tik.unfollow(log.get('user_id'), log.get('user_sec_id'))
            except (RequestException, ProxyError) as e:
                proxy = Account.get('proxy')
                logger.error('%s. %s: Failed to unfollow. %s Requests Error: %s' %(
                    Account.get('id'), Account.get('username'), proxy, e))
                next_time = random.randint(3, 5)
                sc.set('schedule_date', datetime.now() + timedelta(minutes=next_time)).save()
                # Account.set('data.proxy_error', Account.get('data.proxy_error') + 1).save()
                # proxy_error(proxy)
                return False
            except (tiktok.error.ServerError, tiktok.error.CantFollowUserException) as e:
                logger.error('%s. %s: Error. bad user %s: %s' %(
                    Account.get('id'), Account.get('username'), log_username, e))
                log.set('status', 'unfollowed').save()
                continue
            except tiktok.error.LoginExpiredException as e:
                if str(e).lower() == 'invalid parameters':
                    log.set('status', 'unfollowed').save()
                    continue

                logger.exception('%s. %s: %s' %(Account.get('id'), Account.get('username'), e))
                Account.set('login_required', 1).save()
                return False
            except tiktok.error.TooMuchRequestException as e:
                msg = '%s. %s: %s. Will run again in %s hours %s minutes'
                # schedule to 12 hours from now
                # if it slip to next day. start at 00:00 of next day
                # restriction always seems to be lifted after 12hrs or next day GMT
                now = datetime.now()
                next_time =  now + timedelta(hours=12)
                if next_time.day > now.day:
                    next_time = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

                rand_mins = random.randint(5, 15)
                sc.set('schedule_date', next_time + timedelta(minutes=rand_mins)).save()

                secs = (sc.get('schedule_date') - now).total_seconds()
                logger.exception(msg %(Account.get('id'), Account.get('username'), e,
                    int(secs // 3600), (secs % 3600) // 60)
                )
                return False
            except Exception:
                next_time = random.randint(sc.get('settings.next_op_min'), sc.get('settings.next_op_max'))
                logger.exception('%s. %s: unFollowing %s Error. Will run again in %s minutes' % (Account.get('id'),
                    Account.get('username'), log_username, next_time))
                # we don't want to crash forever. do we?. r-reschedule
                sc.set('schedule_date', datetime.now() + timedelta(minutes=next_time)).save()
                return False
            else:
                (
                    UnFollowLogModel()
                    .set('account_id', Account.get('id'))
                    .set('status', 'success')
                    .set('user_id', log.get('user_id'))
                    .set('user_sec_id', log.get('user_sec_id'))
                    .save()
                )

                logger.info('%s. %s: %s successfully unfollowed' %(
                    Account.get('id'), Account.get('username'), log_username))
                max_to_unfollow -= 1
                unfollowed_today += 1
                sc.set('data.following_count', sc.get('data.following_count') - 1).save()
                log.set('status', 'unfollowed').save()
                time.sleep(random.randint(sc.get('settings.sleep_min'), sc.get('settings.sleep_max')))
                if stop_e.is_set():
                    break
            
        logger.info('%s. %s: %s unfollowed today' %(Account.get('id'), Account.get('username'), unfollowed_today))
        next_time = random.randint(sc.get('settings.next_op_min'), sc.get('settings.next_op_max'))
        sc.set('schedule_date', datetime.now() + timedelta(minutes=next_time)).save()
        return True