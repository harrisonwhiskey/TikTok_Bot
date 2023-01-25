import logging, random, time
from datetime import datetime, timedelta
from requests.exceptions import RequestException, ProxyError

from tiktok.tiktok import TikTok
from tiktok.utils import generate_random, username_to_id
import tiktok.error

from models import (
    Database, AccountModel, VideoLikeScheduleModel, VideoLikeLogModel, VideoLikeLogsModel, 
    CommentScheduleModel, CommentLogModel, DeviceModel, FollowScheduleModel, ProxiesModel
)
from utils import login, _login, setup_logger, generate_comment, device_manager, proxy_error, set_new_proxy


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
setup_logger('video_like.log', logger)


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

def auto_video_like(Account, sc, stop_e=None):
    '''
    Account: AccountModel
    sc: VideoLikeScheduleModel
    stop_e: threading.Event
    '''
    if Account.get('login_required') or not sc.get('is_active') or datetime.now() < sc.get('schedule_date'):
        msg = '%s. %s: Auto video like failed to run. Either login required or schedule not active or due'
        logger.error(msg %(Account.get('id'), Account.get('username')))
        return False

    liked_today = (
        VideoLikeLogsModel()
        .where('account_id', '=', Account.get('id'))
        .where('status', '=', 'success')
        .where('liked_date', '>=', 'date', 'now', 'start of day')
        .count()
    )
    if liked_today >= sc.get('settings.max_actions_per_day'):
        logger.info('%s. %s: max follow per day reached. Schedule follow to next day' %(Account.get('id'), Account.get('username')))
        next_day = (datetime.now() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        next_time = random.randint(sc.get('settings.next_schedule_min'), sc.get('settings.next_schedule_max'))
        sc.set('schedule_date', next_day + timedelta(minutes=next_time)).save()
        return False

    max_to_like = random.randint(sc.get('settings.actions_per_op_min'), sc.get('settings.actions_per_op_max'))
    comment_sc = CommentScheduleModel(account_id=Account.get('id'))

    scraper_proxy = ''
    try:
        Tik = login(Account)
        # Tik = _login(Account)
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
                next_time = random.randint(sc.get('settings.next_schedule_min'), sc.get('settings.next_schedule_max'))
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
                    next_time = random.randint(sc.get('settings.next_schedule_min'), sc.get('settings.next_schedule_max'))
                    logger.exception('%s. %s: Error. Will run again in %s minutes' %(Account.get('id'), Account.get('username'), next_time))

                    # we don't want to crash forever. do we?. r-reschedule
                    sc.set('schedule_date', datetime.now() + timedelta(minutes=next_time)).save()
                    return False
        else:
            # invalid user format
            logger.error('%s. %s: %s format is invalid. deleting' %(Account.get('id'), Account.get('username'), user))
            del sc.get('data')['users'][0]
            continue
            
        if sc.get('filters.unique_accross'):
            Log = VideoLikeLogModel(user_id=user_id)
        else:
            Log = VideoLikeLogModel(account_id=Account.get('id'), user_id=user_id)

        if Log.is_available and Log.get('status') == 'success':
            del sc.get('data')['users'][0]
            logger.debug('%s. %s: %s already liked' %(Account.get('id'), Account.get('username'), username))
            continue

        
        # user related filter
        # active_filters = {k:v for k,v in sc.get('filters').items() if v and k in (
        #     'filter_max_followers', 'filter_max_followings', 'filter_blacklist')
        # }
        # if len(active_filters):
        #     logger.debug('%s. %s: Active filters: %s' %(Account.get('id'), Account.get('username'), active_filters))
        #     # get user info
        #     try:
        #         resp = Tik.get_user_info(sec_id=user_sec_id)
        #     except Exception:
        #         raise

        # passed user filters
        failed_counter = 0
        while True:
            try:
                Tik.proxy = scraper_proxy
                videos = Tik.get_user_videos(user_sec_id).videos[:sc.get('settings.like_per_user')]
                break
            except (RequestException, ProxyError) as e:
                logger.error('%s. %s: Scraping user videos (%s). %s requests error: %s' %(
                    Account.get('id'), Account.get('username'), failed_counter, scraper_proxy, e))

                failed_counter += 1
                if failed_counter >= 3:
                    sc.save()
                    return False
                # next_time = random.randint(3, 6)
                # sc.set('schedule_date', datetime.now() + timedelta(minutes=next_time)).save()
                # Account.set('data.proxy_error', Account.get('data.proxy_error') + 1).save()
                # proxy_error(Account.get('proxy'))
                continue
            except tiktok.error.TikTokException:
                next_time = random.randint(2, 3)
                logger.exception('%s. %s: Scraping %s videos error. Will try again in %s minutes' %(
                    Account.get('id'), Account.get('username'), username, next_time))

                Account.set('data.error', Account.get('data.error') + 1).save()
                # if Account.get('data.error') % 3 == 0:
                #     set_new_proxy(Account)

                if Account.get('data.error') % 6 == 0:
                    sc.set('schedule_date', datetime.now() + timedelta(minutes=next_time)).save()
                    # Tik = login(Account)
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

                        # Account.set('data.follow_failed', 0)
                        # Account.set('data.like_failed', 0)
                        # Account.set('data.error', 0).save()
                # if Account.get('data.error') % 2 == 0:
                #     if device_manager(Account, Tik):
                #         logger.info('%s. %s: successfully changed device.' %(Account.get('id'), Account.get('username')))
                #     else:
                #         logger.error('%s. %s: failed to change device. consider adding more device' %(Account.get('id'), Account.get('username')))
                # Account.set('last_action_date', datetime.now()).save()
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
                next_time = random.randint(sc.get('settings.next_schedule_min'), sc.get('settings.next_schedule_max'))
                logger.exception('%s. %s: Scraping user videos error. Will try again in %s minutes' %(Account.get('id'), Account.get('username'), next_time))
                sc.set('schedule_date', datetime.now() + timedelta(minutes=next_time)).save()
                return False

        #TODO:
            # video related filters
            
        # if no video found add user to be followed
        if not videos:
            follow_sc = FollowScheduleModel(account_id=Account.get('id'))
            follow_sc.get('data')['users'].append(user)
            follow_sc.set('data', follow_sc.get('data')).save()

        for video in videos:
            Log = VideoLikeLogModel(account_id=Account.get('id'), video_id=video.id)
            Log.set('user_id', user_id)
            Log.set('user_sec_id', user_sec_id)
            Log.set('data', {
                'liked': {
                    'username': username
                },
                'target': sc.get('data')['target']
            })

            failed_counter = 0
            while True:
                try:
                    logger.info('%s. %s: liking %s video' %(Account.get('id'), Account.get('username'), username))
                    Tik.proxy = Account.get('proxy')
                    Tik.like_video_by_id(video.id)
                except tiktok.error.InvalidOperationException as e:
                    logger.error('%s. %s: %s %s' %(Account.get('id'), Account.get('username'), username, e))
                    break
                except (RequestException, ProxyError) as e:
                    logger.error('%s. %s: Failed to like video. %s Requests error: %s' %(
                        Account.get('id'), Account.get('username'), Account.get('proxy'), e))

                    failed_counter += 1
                    if '502' in str(e):
                        set_new_proxy(Account)
                        Tik = login(Account)

                    if failed_counter >= 3:
                        set_new_proxy(Account)
                        sc.save()
                        Account.save()
                        return False
                    # next_time = random.randint(sc.get('settings.next_schedule_min'), sc.get('settings.next_schedule_max'))
                    # sc.set('schedule_date', datetime.now() + timedelta(minutes=next_time)).save()
                    # Account.set('data.proxy_error', Account.get('data.proxy_error') + 1).save()
                    # proxy_error(Account.get('proxy'))
                    continue
                except tiktok.error.TooMuchRequestException:
                    logger.exception('%s. %s: Error. Will run again in 12hrs' %(Account.get('id'), Account.get('username')))
                    sc.set('schedule_date', datetime.now() + timedelta(hours=12)).save()  # re-schedule 12hrs from now
                    Log.save()
                    return False
                except tiktok.error.AccountDisabledException:
                    logger.exception('%s. %s: Account disabled' %(Account.get('id'), Account.get('username')))
                    Account.set('login_required', 2).save()
                    return False
                except tiktok.error.LikeFailedException:
                    next_time = random.randint(3, 5)
                    Account.set('data.like_failed', Account.get('data.like_failed') + 1)
                    # if Account.get('data.like_failed') % 5 == 0:
                    #     if device_manager(Account, Tik):
                    #         logger.info('%s. %s: successfully changed device.' %(Account.get('id'), Account.get('username')))
                    #     else:
                    #         logger.error('%s. %s: failed to change device. consider adding more device' %(
                    #             Account.get('id'), Account.get('username')))
                    #     del sc.get('data')['users'][0]
                    #     next_time = random.randint(10, 20)
                    
                    if Account.get('data.like_failed') % 10 == 0:
                        next_time = random.randint(5, 10)

                    Account.set('last_action_date', datetime.now()).save()

                    msg = '%s. %s: Error. Failed to like %s. will run again %s mins from now'
                    logger.error(msg %(Account.get('id'), Account.get('username'), username, next_time))
                    sc.set('schedule_date', datetime.now() + timedelta(minutes=next_time)).save()
                    Account.save()
                    return False
                except Exception:
                    next_time = random.randint(sc.get('settings.next_schedule_min'), sc.get('settings.next_schedule_max'))
                    logger.exception('%s. %s: Failed to like video. Will try again in %s' %(Account.get('id'), Account.get('username'), next_time))
                    sc.set('schedule_date', datetime.now() + timedelta(minutes=next_time)).save()
                    Log.save()
                    return False
                else:
                    logger.info('%s. %s: liking %s video successful' %(Account.get('id'), Account.get('username'), username))
                    Log.set('status', 'success').save()
                    max_to_like -= 1
                    liked_today += 1

                    # comment after like
                    # if (comment_sc.is_available and not comment_sc.is_disabled and comment_sc.get('schedule_date') <= datetime.now()):
                    if False:
                        try:
                            Log = CommentLogModel()
                            resp = Tik.comment(generate_comment() + ' ' + username, video.id)
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
                        except (RequestException, ProxyError) as e:
                            logger.error('%s. %s: comment failed. %s Network Error -> %s' %(
                                Account.get('id'), Account.get('username'), Account.get('proxy'), e))
                            # Account.set('data.proxy_error', Account.get('data.proxy_error') + 1).save()
                            proxy_error(Account.get('proxy'))
                        except (tiktok.error.CommentException, tiktok.error.VideoNotExist) as e:
                            logger.error('%s. %s: %s Failed to comment. -> %s' %(Account.get('id'), Account.get('username'), username, e))
                        except tiktok.error.TooMuchRequestException:
                            msg = '%s. %s: Comment Error. Both like and comment Will run again in %s hours %s minutes'
                            # schedule to 12 hours from now
                            # if it slip to next day. start at 00:00 of next day
                            # restriction always seems to be lifted after 12hrs or next day GMT
                            now = datetime.now()
                            next_time =  now + timedelta(hours=12)
                            if next_time.day > now.day:
                                next_time = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

                            rand_mins = random.randint(5, 15)
                            comment_sc.set('schedule_date', next_time + timedelta(minutes=rand_mins)).save()
                            sc.set('schedule_date', next_time + timedelta(minutes=rand_mins)).save()

                            secs = (now - sc.get('schedule_date')).total_seconds()
                            logger.exception(msg %(Account.get('id'), Account.get('username'),
                                int(secs // 3600), (secs % 3600) // 60)
                            )
                            return False
                        except tiktok.error.CommentBlockedException:
                            logger.exception('%s. %s: comment blocked.' %(Account.get('id'), Account.get('username')))
                            comment_sc.set('schedule_date',  datetime.now() + timedelta(days=1)).save()
                            # return False
                        except tiktok.error.AccountDisabledException:
                            logger.exception('%s. %s: Account disabled' %(Account.get('id'), Account.get('username')))
                            Account.set('login_required', 2).save()
                            return False
                        except Exception:
                            logger.exception('%s. %s: %s Failed to comment.' %(Account.get('id'), Account.get('username'), username))
                    else:
                        logger.info('%s. %s: comment is not active' %(Account.get('id'), Account.get('username')))

                    if max_to_like > 0:
                        time.sleep(random.randint(sc.get('settings.sleep_min'), sc.get('settings.sleep_max')))
                    break

        del sc.get('data')['users'][0]
        if max_to_like <= 0:
            break
        
    logger.info('%s. %s: %s Videos liked today' %(Account.get('id'), Account.get('username'), liked_today))
    next_time = random.randint(sc.get('settings.next_schedule_min'), sc.get('settings.next_schedule_max'))
    sc.set('schedule_date', datetime.now() + timedelta(minutes=next_time)).save()
    return True