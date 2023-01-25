import logging, random, time
import functools
import threading
import queue, json
from concurrent import futures
from datetime import datetime, timedelta
from requests.exceptions import RequestException, ProxyError

from tiktok.tiktok import TikTok
from tiktok.utils import generate_random, username_to_id
import tiktok.error

from models import (
    Database, AccountModel, CommentScheduleModel, CommentLogModel, DeviceModel,
    CommentLogsModel, ProxiesModel, CommentSchedulesModel, UnFollowSchedulesModel, FollowScheduleModel
)
from utils import login, _login, setup_logger, generate_comment, set_new_proxy
from auto_unfollow import auto_unfollow

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
setup_logger('auto_comment.log', logger)


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
        if target == 'url_list':
            raise NotImplementedError
    return


def mention(Account, Tik, user, video_ids):
    if video_ids:
        video_id = random.choice(video_ids)
    else:
        logger.error('video ids to mention empty!')
        return

    try:
        text = ''
        text_extra = []
        username, user_id, user_sec_id = user
        text += f'@{username} '

        start = len(text) - (len(username) + 2)
        text_extra.append(
            json.dumps({
                "at_user_type": "",
                "boldText": False,
                "color": 0,
                "end": start + len(username) + 1,
                "isClickable": True,
                "is_commerce": False,
                "star_atlas_tag": False,
                "start": start,
                "sticker_source": 0,
                "type": 0,
                "user_id": str(user_id)
            }, separators=(",", ":"))
        )
        resp = Tik.comment(text, video_id, text_extra=text_extra)
    except tiktok.error.CommentGhosted as e:
        logger.error('%s. %s: %s Failed to mention. ghosted -> %s' %(Account.get('id'), Account.get('username'), username, e))
    except (tiktok.error.VideoNotExist, tiktok.error.CommentException) as e:
        logger.error('%s. %s: %s Failed to mention. -> %s' %(Account.get('id'), Account.get('username'), username, e))
        print('%s video don\'t exist.' %(video_id))
        video_ids.remove(video_id)
    except (RequestException, ProxyError) as e:
        logger.error('%s. %s: Failed to mention. %s Requests error: %s' %(
            Account.get('id'), Account.get('username'), Account.get('proxy'), e))

        set_new_proxy(Account)
        Tik = login(Account)
    except Exception:
        logger.exception('%s. %s: %s Failed to mention.' %(Account.get('id'), Account.get('username'), username))
    else:
        (
            CommentLogModel(account_id=Account.get('id'))
            .set('status', 'success')
            .set('user_id', user_id)
            .set('user_sec_id', user_sec_id)
            .set('video_id', video_id)
            .set('comment_id', resp.comment.id)
            .set('comment', resp.comment.text)
            .set('data', {
                'username': username
            })
            .save()
        )
        logger.info('%s. %s: %s mentioned successful on %s' %(Account.get('id'), Account.get('username'), username, video_id))


def auto_comment(Account, sc, stop_e=None, video_ids=[]):
    '''
    Account: AccountModel
    sc: CommentScheduleModel
    stop_e: threading.Event
    '''
    if Account.get('login_required') or not sc.get('is_active') or datetime.now() < sc.get('schedule_date'):
        msg = '%s. %s: Auto comment failed to run. Either login required or schedule not active or due'
        logger.error(msg %(Account.get('id'), Account.get('username')))
        return False

    commented_today = (
        CommentLogsModel()
        .where('account_id', '=', Account.get('id'))
        .where('status', '=', 'success')
        .where('commented_date', '>=', 'date', 'now', 'start of day')
        .count()
    )
    if commented_today >= sc.get('settings.max_per_day'):
        logger.info('%s. %s: max comment per day reached. Schedule comment to next day' %(Account.get('id'), Account.get('username')))
        next_day = (datetime.now() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        next_time = random.randint(sc.get('settings.next_op_min'), sc.get('settings.next_op_min'))
        sc.set('schedule_date', next_day + timedelta(minutes=next_time)).save()
        return False

    max_to_comment = random.randint(sc.get('settings.op_min'), sc.get('settings.op_max'))
    # scraper_proxy = 'bodybad1:bodybad1@gate.dc.smartproxy.com:20000'
    scraper_proxy = ''

    try:
        Tik = login(Account)
    except Exception:
        logger.error('%s. %s login failed' %(Account.get('id'), Account.get('username')))
        return False

    while stop_e and not stop_e.is_set() and not sc.is_disabled:
        if len(sc.get('data')['users']) == 0:
            '''no users in cache let's randomly choose a source from active target 
            and scrape or fetch users and put in cache(data field). targets: (followers, followings
            users: scrape from somewhere else)'''
            logger.info('%s. %s: No cached users. Trying to scrape' %(Account.get('id'), Account.get('username')))
            scrape_users(Account, sc, Tik)

            # if we aint get any users to follow shedule and return
            if len(sc.get('data')['users']) == 0:
                logger.info('%s. %s: No users to like their video. auto video like re-scheduled' %(Account.get('id'), Account.get('username')))
                next_time = random.randint(sc.get('settings.next_op_min'), sc.get('settings.next_op_min'))
                sc.set('schedule_date', datetime.now() + timedelta(minutes=next_time)).save()
                return False
            
        sc.set('data', sc.get('data'))  # trigger save. a stupid hack that needs addressing

        username = user_id = user_sec_id = None
        user = sc.get('data')['users'][0]  # get user from cache

        if len(user) == 3:
            username, user_id, user_sec_id = user 
        elif type(user) == str or len(user) == 1:
            logger.debug('%s. %s: selected to like: %s' %(Account.get('id'), Account.get('username'), username))
            username = user if type(user) is str else user[0]
            if username.startsWith('https'):
                # is url
                url = url.strip('/').split('/')
            else:
                try:
                    user_id, user_sec_id = username_to_id(username)
                except ValueError:
                    # if username_to_id failed to find user
                    logger.exception('%s. %s: ValueError' %(Account.get('id'), Account.get('username')))
                    del sc.get('data')['users'][0]
                    continue
                except Exception:
                    # requests error. interet down??
                    next_time = random.randint(sc.get('settings.next_op_min'), sc.get('settings.next_op_min'))
                    logger.exception('%s. %s: Error. Will run again in %s minutes' %(Account.get('id'), Account.get('username'), next_time))

                    # we don't want to crash forever. do we?. r-reschedule
                    sc.set('schedule_date', datetime.now() + timedelta(minutes=next_time)).save()
                    return False
        else:
            # invalid user format
            logger.error('%s. %s: %s format is invalid. deleting' %(Account.get('id'), Account.get('username'), user))
            del sc.get('data')['users'][0]
            continue
            
        failed_counter = 0
        while True:
            try:
                # Tik.proxy = scraper_proxy
                videos = Tik.get_user_videos(user_sec_id).videos[:sc.get('settings.comment_per_user')]
                break
            except (RequestException, ProxyError) as e:
                logger.error('%s. %s: Scraping user videos (%s). %s requests error: %s' %(
                    Account.get('id'), Account.get('username'), failed_counter, scraper_proxy, e))

                failed_counter += 1
                
                set_new_proxy(Account, True)
                Tik = login(Account)
                if failed_counter >= 3:
                    sc.save()
                    return False
                continue
            except tiktok.error.TikTokException:
                next_time = random.randint(sc.get('settings.next_op_min'), sc.get('settings.next_op_min'))
                logger.exception('%s. %s: Scraping %s videos error. Will try again in %s minutes' %(
                    Account.get('id'), Account.get('username'), username, next_time))
                
                Account.set('data.error', Account.get('data.error') + 1).save()
                
                if Account.get('data.error') % 10 == 0:
                    next_day = (datetime.now() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    sc.set('schedule_date', next_day + timedelta(minutes=next_time)).save()
                else:
                    sc.set('schedule_date', datetime.now() + timedelta(minutes=next_time)).save()
                return False
            except tiktok.error.ServerError:
                logger.error('%s. %s: bad user %s. cant scrape videos' %(
                    Account.get('id'), Account.get('username'), username))
                videos = []
                break
            except tiktok.error.AccountDisabledException:
                logger.exception('%s. %s: Account disabled' %(Account.get('id'), Account.get('username')))
                sc.save()
                Account.set('login_required', 2).save()
                return False
            except tiktok.error.LoginExpiredException as e:
                logger.error('%s. %s: %s' %(Account.get('id'), Account.get('username'), e))
                sc.save()
                Account.set('login_required', 1).save()
                return False
            except Exception:
                next_time = random.randint(sc.get('settings.next_op_min'), sc.get('settings.next_op_min'))
                logger.exception('%s. %s: Scraping user videos error. Will try again in %s minutes' %(Account.get('id'), Account.get('username'), next_time))
                sc.set('schedule_date', datetime.now() + timedelta(minutes=next_time)).save()
                return False

        if not videos:
            follow_sc = FollowScheduleModel(account_id=Account.get('id'))
            follow_sc.get('data')['users'].append(user)
            follow_sc.set('data', follow_sc.get('data')).save()
            # mention(Account, Tik, user, video_ids)

        for video in videos:
            Log = CommentLogModel(account_id=Account.get('id'), user_id=user_id, video_id=video.id)
            if Log.is_available and Log.get('status') == 'success':
                logger.debug('%s. %s: %s video already commented' %(Account.get('id'), Account.get('username'), username))
                continue

            failed_counter = 0
            while True:
                try:
                    Tik.proxy = Account.get('proxy')
                    resp = Tik.comment(generate_comment() + ' ' + username, video.id)
                except (RequestException, ProxyError) as e:
                    logger.error('%s. %s: Failed to comment. %s Requests error: %s' %(
                        Account.get('id'), Account.get('username'), Account.get('proxy'), e))

                    set_new_proxy(Account, True)
                    Tik = login(Account)

                    if failed_counter >= 3:
                        sc.save()
                        Account.save()
                        return False
                    continue
                except tiktok.error.CommentGhosted as e:
                    logger.error('%s. %s: %s Failed to comment -> %s' %(Account.get('id'), Account.get('username'), username, e))

                    Account = AccountModel(id=Account.get('id'))
                    Account.set('data.comment_failed', Account.get('data.comment_failed') + 1).save()
                    if Account.get('data.comment_failed') % 4 == 0:
                        next_time = random.randint(300, 360)
                        set_new_proxy(Account, True)
                        Tik = login(Account, force_login_flow=True)
                    else:
                        next_time = random.randint(25, 45)

                    if Account.get('data.comment_failed') >= 10:
                        # tags = Account.get('tags')
                        # tags = tags + ', C_STOP' if tags else 'C_STOP'
                        # Account.set('tags', tags).save()
                        # sc.disable()
                        set_new_proxy(Account, True)
                        next_time = 24 * 60
                    
                    # set_new_proxy(Account)
                    msg = '%s. %s: Too many ghosted. will run again %s mins from now'
                    logger.error(msg %(Account.get('id'), Account.get('username'), next_time))
                    del sc.get('data')['users'][0]

                    sc.set('schedule_date', datetime.now() + timedelta(minutes=next_time)).save()
                    return False
                except (tiktok.error.VideoNotExist, tiktok.error.CommentException) as e:
                    logger.error('%s. %s: %s Failed to comment. -> %s' %(Account.get('id'), Account.get('username'), username, e))
                    
                    follow_sc = FollowScheduleModel(account_id=Account.get('id'))
                    follow_sc.get('data')['users'].append(user)
                    follow_sc.set('data', follow_sc.get('data')).save()
                    # mention(Account, Tik, user, video_ids)
                    videos.clear()
                    break
                except tiktok.error.TooMuchRequestException:
                    msg = '%s. %s: Comment Error. Comment Will run again in %s hours %s minutes'
                    # schedule to 12 hours from now
                    # if it slip to next day. start at 00:00 of next day
                    # restriction always seems to be lifted after 12hrs or next day GMT
                    now = datetime.now()
                    next_time =  now + timedelta(hours=12)
                    if next_time.day > now.day:
                        next_time = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

                    rand_mins = random.randint(5, 15)
                    sc.set('schedule_date', next_time + timedelta(minutes=rand_mins)).save()

                    secs = (now - sc.get('schedule_date')).total_seconds()
                    logger.exception(msg %(Account.get('id'), Account.get('username'),
                        int(secs // 3600), (secs % 3600) // 60)
                    )
                    return False
                except tiktok.error.CommentBlockedException:
                    logger.exception('%s. %s: comment blocked.' %(Account.get('id'), Account.get('username')))
                    sc.set('schedule_date',  datetime.now() + timedelta(days=1)).save()
                    return False
                except tiktok.error.AccountDisabledException:
                    logger.exception('%s. %s: Account disabled' %(Account.get('id'), Account.get('username')))
                    Account.set('login_required', 2).save()
                    return False
                except tiktok.error.LoginExpiredException as e:
                    logger.error('%s. %s: %s' %(Account.get('id'), Account.get('username'), e))
                    Account.set('login_required', 1).save()
                    return False
                except tiktok.error.TikTokException:
                    logger.exception('%s. %s: %s Failed to comment.' %(Account.get('id'), Account.get('username'), username))
                    del sc.get('data')['users'][0]
                    sc.save()
                    return False
                except Exception:
                    logger.exception('%s. %s: %s Failed to comment.' %(Account.get('id'), Account.get('username'), username))
                    return False
                else:
                    (
                        Log.set('account_id', Account.get('id'))
                        .set('status', 'success')
                        .set('user_id', user_id)
                        .set('user_sec_id', user_sec_id)
                        .set('video_id', video.id)
                        .set('comment_id', resp.comment.id)
                        .set('comment', resp.comment.text)
                        .set('data', {
                            'username': username
                        })
                        .save()
                    )

                    logger.info('%s. %s: %s comment successful' %(Account.get('id'), Account.get('username'), username))
                    max_to_comment -= 1
                    commented_today += 1
                    Account = AccountModel(id=Account.get('id'))
                    Account.set('data.comment_failed', 0).save()

                    if max_to_comment > 0:
                        time.sleep(random.randint(sc.get('settings.sleep_min'), sc.get('settings.sleep_max')))
                    break

        del sc.get('data')['users'][0]
        if max_to_comment <= 0:
            break
        
    logger.info('%s. %s: %s Videos commented today' %(Account.get('id'), Account.get('username'), commented_today))
    next_time = random.randint(sc.get('settings.next_op_min'), sc.get('settings.next_op_min'))
    sc.set('schedule_date', datetime.now() + timedelta(minutes=next_time)).save()
    return True



def finished_callback(account_id, running_accs, future):
    try:
        del running_accs[account_id]
    except KeyError:
        print('failed to delete account_id: %s' % account_id)
    
    logger.debug('Account: %s finished execution' % account_id)
    try:
        result = future.result()
        logger.debug('Account: %s returned: %s' % (account_id, result))
    except Exception:
        logger.exception('Account: %s Error' % account_id)
    return

def main_worker(schedule_q, running_accs, max_workers, stop_e, video_ids):
    '''
    Here is where we check for due actions.
    But first like implement auto-follow
    '''
    executor = futures.ThreadPoolExecutor(max_workers)
    logger.debug('Main worker started with %s workers..' %max_workers)

    while not stop_e.is_set():
        while not stop_e.is_set():
            try:
                Account, sc, action = schedule_q.get(timeout=0.01)
            except queue.Empty:
                logger.debug('Empty schedule main_worker')
                break
            else:
                logger.debug('%s. %s scheduled to %s' %(Account.get('id'), Account.get('username'), action))
                if action == UnFollowSchedulesModel:
                    future = executor.submit(auto_unfollow, Account, sc, stop_e)
                    future.add_done_callback(functools.partial(finished_callback, Account.get('id'), running_accs))
                elif action == CommentSchedulesModel:
                    future = executor.submit(auto_comment, Account, sc, stop_e, video_ids)
                    future.add_done_callback(functools.partial(finished_callback, Account.get('id'), running_accs))
        time.sleep(60)
    
    # stop signalled
    executor.shutdown(wait=True)
    logger.debug('Exiting main worker..')
    return 0

def actions_scheduler(schedule_q, running_accs, stop_e):
    ''' put due actions on schedule queue to be run '''
    logger.debug('acctions scheduler started..')

    actions = [UnFollowSchedulesModel, CommentSchedulesModel]
    today_date = datetime.now()
    # proxy_idx = 0
    while not stop_e.is_set():
        # proxies = (
        #     ProxiesModel()
        #     .where('rotate', '=', 1)
        #     .fetch_data()
        # )
        for action in actions:
            schedules = (
                action()
                .fetch_active_due_schedules()
            )
            logger.debug('No. of due accounts: %s ..' %(len(schedules)))

            for sc in schedules:
                Account = AccountModel(id=sc.get('account_id'))
                if Account.get('id') in running_accs:
                    continue

                # if len(proxies):
                #     Account.set('proxy', proxies[proxy_idx].get_proxy())
                #     proxy_idx += 1
                #     proxy_idx = proxy_idx % len(proxies)

                schedule_q.put((Account, sc, action))
                running_accs[Account.get('id')] = (type(sc).__name__, int(time.time()))
                Account = sc = None
                
        time.sleep(60)

        # check accounts
        if today_date.day != datetime.now().day:
            today_date = datetime.now()
            print('%s: Starting check accounts info')
            accs = (
                AccountsModel()
                .where('tags', 'like', '%test%')
                .where('login_required', '=', 0)
                .fetch_data()
            )
            threading.Thread(target=check_accounts_info, kwargs={'accs':accs, 'console_log':False}).start()

        # sometimes running schedule get stack for hours
        # remove schedule still active for 1 hour so it can be re-added
        try:
            running = next(iter( running_accs.items() ))
        except StopIteration:
            pass
        else:
            if time.time() - running[1][1] >= 100 * 60:
                # del running_accs[running[0]]
                # logger.info('Account id: %s was stacked. removed from running_accs' %running[0])
                print('Account id: %s is stacked for 100 minutes' %running[0])
    logger.debug('Exiting actions_scheduler..')
    return 0


if __name__ == "__main__":
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.CRITICAL)
    setup_logger('comment_logs.log', root_logger, True)

    schedule_q = queue.Queue()
    stop_e = threading.Event()
    max_workers = 20 # max threads

    # current active account_id: (ActionClassName, time.time())
    # updated in actions_scheduler 
    running_accs = {}

    # video ids to add mentions
    video_ids = ['6991133735844400389', '6991132859767459078', '6991131965168635141', '6991131602579426565', '6991132340596509957']

    t1 = threading.Thread(target=actions_scheduler, args=(
        schedule_q, running_accs, stop_e))
    t1.start()

    time.sleep(1)

    t2 = threading.Thread(target=main_worker, args=(
        schedule_q, running_accs, max_workers, stop_e, video_ids))
    t2.start()