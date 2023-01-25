import time, os, sys
import functools
import threading
import queue
import logging
import random
import shutil
from datetime import datetime
from concurrent import futures
import requests
from sqlite3 import OperationalError

from tiktok.tiktok import TikTok
import tiktok.error
from tiktok.utils import username_to_id

from models import (
    Database, AccountModel, FollowScheduleModel, VideoLikeScheduleModel, CommentScheduleModel, UnFollowScheduleModel,
    FollowSchedulesModel, VideoLikeSchedulesModel, CommentSchedulesModel, UnFollowSchedulesModel,
    AccountsModel, FollowLogsModel, VideoLikeLogsModel, CommentLogsModel, UnFollowLogsModel,
    ProxyModel, ProxiesModel, FollowLogModel
)
from auto_follow import auto_follow
from auto_video_like import auto_video_like
from utils import Response, setup_logger, time_int, login, device_manager, set_new_proxy


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
setup_logger('app.log', logger)

# d_logger = logging.getLogger('debug')
# d_logger.setLevel(logging.DEBUG)
# setup_logger('debug_00.log', d_logger)


# keep track of accounts disabled in a day
# updated in finished_callback when action return account_disabled or login_required exception
# reset to 0 when day begins in actions_scheduler
ACCOUNTS_DISABLED = 0

def counter_today(action, account_id):
    '''
    :acc: username or account id
    '''
    if action == 'follow':
        action = FollowLogsModel
        action_col = 'followed_date'
    elif action == 'like':
        action = VideoLikeLogsModel
        action_col = 'liked_date'
    elif action == 'comment':
        action = CommentLogsModel
        action_col = 'commented_date'
    else:
        raise TypeError('%s is not a valid action' %action)

    return action().where('account_id', '=', account_id).where('status', '=', 'success').where(action_col, '>=', 'date', 'now', 'start of day').count()

    
def stats(tags=None):
    if tags:
        accounts = AccountsModel().where('tags', 'like', f'%{tags}%').fetch_data()
    else:
        accounts = AccountsModel().fetch_data()

    print('{:<5} {:<22}{:<10}{:<10}{:<10}\n'.format('id', 'username', 'follows', 'likes', 'comments'))
    for acc in accounts:
        value = (   
            acc.get('id'),
            acc.get('username'),
            counter_today('follow', acc.get('id')),
            counter_today('like', acc.get('id')),
            counter_today('comment', acc.get('id'))
        )
        print('{:<5} {:<22}{:<10}{:<10}{:<10}'.format(*value))
    

def add_account(
    username, password, email='', phone='', proxy=None, tags='',
    force_login=False, reset_device=False, device=False,
    folder=None):
    Account = AccountModel(username=username)
    is_new = not Account.is_available

    if device:
        device_manager(Account, new_account=True)

    if is_new:
        # check for valid tiktkok username / empty username
        (
            Account.set('username', username)
            .set('password', password)
            .set('email', email)
            .set('phone', phone)
            .set('proxy', proxy)
            .set('tags', tags)
            .set('login_required', 1)
        )
    if Account.get('login_required') == 1 or force_login or reset_device:
        tk = TikTok(folder)
        tk.login_flow = False
        logger.info('%s: Atempt log in..' %Account.get('username'))

        while True:
            try:
                login_resp = tk.login(
                    Account.get('username'), Account.get('password'), proxy=Account.get('proxy'),
                    force_login=force_login, reset_device=reset_device
                )
                # login_resp = Response()
                (
                    Account.set('login_required', 0)
                    .set('email', tk.settings.get('email'))
                    .set('phone', tk.settings.get('phone'))
                    .set('password', tk.settings.get('pwd'))
                    .set('user_id', tk.settings.get('user_id'))
                    .set('user_sec_id', tk.settings.get('sec_user_id'))
                    .set('proxy', tk.settings.get('proxy'))
                    .set('last_login', datetime.now())
                )
                logger.info('%s: loggin success' %Account.get('username'))
                break
            except tiktok.error.CaptchaErrorException as e:
                # captcha can be stuborn to solve
                logger.debug('%s: - %s' %(Account.get('username'), e))
                while True:
                    try:
                        tk.solve_captcha()
                        break
                    except tiktok.error.CaptchaErrorException as e:
                        logger.debug('%s: - %s' %(Account.get('username'), e))
                        continue
            except tiktok.error.AccountDisabledException as e:
                logger.exception('%s: Account disabled' %(Account.get('username')))
                Account.set('last_login', datetime.now()).set('login_required', 2)
                break
            except Exception as e:
                logger.exception('%s: Failed to login' %(Account.get('username')))
                break
        Account.save()

    for model in (FollowScheduleModel, VideoLikeScheduleModel, CommentScheduleModel, UnFollowScheduleModel):
        sc = model(account_id=Account.get('id'))
        if not sc.is_available:
            sc.set('tags', Account.get('tags'))
            sc.save()

    return Account


def add_new_account(
    username, password, email='', phone='', proxy='', tags='',
    force_login=True, reset_device=False, folder=None):
    Account = AccountModel(username=username)
    is_new = not Account.is_available

    if is_new:
        # check for valid tiktkok username / empty username
        (
            Account.set('username', username)
            .set('password', password)
            .set('email', email)
            .set('phone', phone)
            .set('proxy', proxy)
            .set('tags', tags)
            .set('login_required', 1)
            .save()
        )
    
    for model in (FollowScheduleModel, VideoLikeScheduleModel, CommentScheduleModel, UnFollowScheduleModel):
        sc = model(account_id=Account.get('id'))
        if not sc.is_available:
            sc.set('tags', Account.get('tags'))
            sc.save()



            
def add_accounts(usernames, tags=''):
    if type(usernames) is list:
        pass
    elif type(usernames) is str and usernames.endswith('.txt'):
        with open(usernames, 'r') as f:
            usernames = f.readlines()
    else:
        raise TypeError('Invalid argument')
    
    for idx, username in enumerate(usernames):
        username = username.strip()
        print('%s. %s adding account' %(idx, username))
        try:
            add_account(username, '@@freeman', tags=tags, force_login=False)
        except Exception as e:
            print(e)

def delete_account(Account, on_disk=True):
    if on_disk:
        Tik = TikTok()
        Tik._set_user(Account.get('username'))
        Tik.settings.delete()
    return Account.delete()        

def replace_account(ac, new_user, new_pwd, login_flow=False, folder=None):
    Tik = TikTok(folder)
    if not Tik.settings.has_user(new_user):
        print('new user %s does not exist in folder %s' %(new_user, folder))
    
    Tik.login_flow = login_flow
    Tik.login(new_user, new_pwd, proxy='')

    tk = login(ac, folder, login_flow=False)
    tk.settings.delete()
    (
        ac.set('username', new_user)
        .set('password', Tik.settings.get('pwd'))
        .set('email', Tik.settings.get('email'))
        .set('phone', Tik.settings.get('phone'))
        .set('user_id', Tik.settings.get('user_id'))
        .set('user_sec_id', Tik.settings.get('sec_user_id'))
        .set('last_login', datetime.now())
        .set('tags', 'warm-up')
        .set('login_required', 1)
        .save()
    )

def update_tags(from_table='accounts'):
    if from_table == 'accounts':
        action = AccountsModel
    elif from_table == 'follow':
        action = FollowSchedulesModel
    elif from_table == 'like':
        action = VideoLikeSchedulesModel
    else:
        raise TypeError('Enter vaild command')

    if action == AccountsModel:
        accs = AccountsModel().fetch_data()
        for ac in accs:
            FollowScheduleModel(account_id=ac.get('id')).set('tags', ac.get('tags')).save()
            VideoLikeScheduleModel(account_id=ac.get('id')).set('tags', ac.get('tags')).save()
            CommentScheduleModel(account_id=ac.get('id')).set('tags', ac.get('tags')).save()
    elif action == FollowSchedulesModel:
        schedules = FollowSchedulesModel().fetch_data()
        for sc in schedules:
            VideoLikeScheduleModel(account_id=sc.get('account_id')).set('tags', sc.get('tags')).save()
            AccountModel(id=sc.get('account_id')).set('tags', sc.get('tags')).save()
    elif action == VideoLikeSchedulesModel:
        schedules = VideoLikeSchedulesModel().fetch_data()
        for sc in schedules:
            FollowScheduleModel(account_id=sc.get('account_id')).set('tags', sc.get('tags')).save()
            AccountModel(id=sc.get('account_id')).set('tags', sc.get('tags')).save()


def add_proxy(proxy, port, username='', password='', tags='', rotate=True):
    p  = ProxyModel(proxy=proxy, port=port)
    if p.is_available:
        print(f'{proxy}:{port} alrady exist')
        return p
    (
        p.set('username', username)
        .set('password', password)
        .set('tags', tags)
        .set('rotate', int(rotate))
        .save()
    )
    return p

def add_proxies(proxies):
    if type(proxies) is not list:
        raise TypeError('proxies must be list')

    for proxy in proxies:
        print('adding proxy: %s' % proxy)
        args = []
        proxy = proxy.split('@')
        for arg in proxy:
            args.extend(arg.split(':'))
        
        add_proxy(*args)


def finished_callback(account_id, running_accs, future):
    try:
        del running_accs[account_id]
    except KeyError:
        print('failed to delete account_id: %s' % account_id)
    
    logger.debug('Account: %s finished execution' % account_id)
    try:
        result = future.result()
        logger.debug('Account: %s returned: %s' % (account_id, result))
    except (tiktok.error.AccountDisabledException, tiktok.error.LoginExpiredException) as e:
        logger.error('Account: %s disabled: %s' % (account_id, e))
        global ACCOUNTS_DISABLED
        ACCOUNTS_DISABLED += 1
    except Exception:
        logger.exception('Account: %s Error' % account_id)
    return


def main_worker(schedule_q, running_accs, max_workers, stop_e):
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
                if action == FollowSchedulesModel:
                    future = executor.submit(auto_follow, Account, sc, stop_e)
                    future.add_done_callback(functools.partial(finished_callback, Account.get('id'), running_accs))
                elif action == VideoLikeSchedulesModel:
                    future = executor.submit(auto_video_like, Account, sc, stop_e)
                    future.add_done_callback(functools.partial(finished_callback, Account.get('id'), running_accs))
                sc = action = None
        time.sleep(60)
    
    # stop signalled
    executor.shutdown(wait=True)
    logger.debug('Exiting main worker..')
    return 0


def actions_scheduler(schedule_q, running_accs, stop_e):
    ''' put due actions on schedule queue to be run '''
    logger.debug('acctions scheduler started..')
    actions = [FollowSchedulesModel, VideoLikeSchedulesModel]
    proxy_idx = 0
    today_date = datetime.now()
    update_after_12 = True
    global ACCOUNTS_DISABLED

    while not stop_e.is_set():
        proxies = (
            ProxiesModel()
            .where('rotate', '=', 1)
            .order_by('last_action_date', 'ASC')
            .fetch_data()
        )
        
        for action in actions:
            schedules = (
                action()
                .fetch_active_due_schedules()
            )
            logger.debug('No. of due %s: %s ..' %(action, len(schedules)))
            for sc in schedules:
                Account = AccountModel(id=sc.get('account_id'))
                if Account.get('id') in running_accs:
                    continue
                
                if len(proxies):
                    Account.set('proxy', proxies[proxy_idx].get_proxy())
                    proxies[proxy_idx].set('last_action_date', datetime.now()).save()
                    proxy_idx += 1
                    proxy_idx = proxy_idx % len(proxies)

                schedule_q.put((Account, sc, action))
                running_accs[Account.get('id')] = (type(sc).__name__, int(time.time()))
                Account = sc = None
        time.sleep(30)

        # future comment here
        if today_date.day != datetime.now().day:
            today_date = datetime.now()
            ACCOUNTS_DISABLED = 0
            print('%s: Starting check accounts info')
            threading.Thread(target=check_accounts_info, kwargs={'no_proxy':True}).start()
            update_after_12 = True
            # print('it is time to stop')
            # stop_e.set()
        else:
            if  update_after_12 and time_int(datetime.now()) >= 1200:
                print('%s: Starting check accounts info')
                threading.Thread(target=check_accounts_info, kwargs={'no_proxy':True}).start()
                update_after_12 = False
        
        if ACCOUNTS_DISABLED >= 50:
            print('stopping all accounts. Accounts disabled today: %s' %ACCOUNTS_DISABLED)
            accs = AccountsModel().where('login_required', '=', 0).fetch_data()
            for ac in accs:
                ac.set('login_required', 500).save()

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


def main():
    schedule_q = queue.Queue()
    # lock = threading.Lock()
    stop_e = threading.Event()
    max_workers = 30 # max threads

    # current active account_id: (ActionClassName, time.time())
    # updated in actions_scheduler 
    running_accs = {}

    t1 = threading.Thread(target=actions_scheduler, args=(
        schedule_q, running_accs, stop_e))
    t1.start()

    time.sleep(1)

    t2 = threading.Thread(target=main_worker, args=(
        schedule_q, running_accs, max_workers, stop_e))
    t2.start()
    
    # while True:
    #     try:
    #         option = input('> ').strip()
    #         exit_words = ('stop', 'quit', 'exit', 'exit()')
    #         if option in exit_words:
    #             raise KeyboardInterrupt
    #         try:
    #             exec(option)
    #         except Exception as e:
    #             msg = "An exception of type {0} occurred: {1}"
    #             print(msg.format(type(e).__name__, e))
    #         finally:
    #             print()
    #     except KeyboardInterrupt:
    #         stop_e.set()
    #         t1.join()
    #         t2.join()
    #         raise SystemExit


def rand_username():
    keyword = [
        'free_followers',
        'fre33_follows',
        'get_followers',
        'tiktok_followers',
        'free.follows',
        'get.follows',
        'tiktok.follows',
        'get_free_followers',
        'get_fre33_follows',
        'instant_followers',
        'instant_follows',
        'tiktok_famous',
        'tiktok_fame',
        'tiktok_f0ll0wers'
    ]
    return (
        f'{random.choice(["", "", "_"])}'
        f'{random.choice(keyword)}'
        f'{random.choice(["", ".", "_"])}'
        f'{"".join(str(random.randint(0, 9)) for _ in range(random.randint(1, 4)))}'
    )

def rename_account(Account, username=None):
    try:
        Tik = login(Account)
    except Exception:
        raise

    while True:
        if not username:
            u = rand_username()
        else:
            u = username

        try:
            Tik.change_username(u)
        except tiktok.error.UsernameTakenException:
            if username:
                raise
            continue
        except Exception:
            raise
        else:
            Account.set('data.old_name', Account.get('username')).save()
            Account.set('username', u).save()
            return True


def check_accounts():
    def check(ac):
        try:
            print('logging in %s' %ac.get('username'))
            login(ac, force_login_flow=True)
        except Exception as e:
            print('%s: %s' %(ac.get('username'), e))

    accounts = AccountsModel().where('login_required', '=', 0).where('tags', 'like', f'%002%').fetch_data()

    while True:
        workers = min(10, len(accounts))
        print('Accounts left: %s' %len(accounts))

        grabs = accounts[:workers]
        with futures.ThreadPoolExecutor(max_workers=workers) as executor:
            result = executor.map(check, grabs)
            print(list(result))

        del accounts[:workers]
        if not accounts:
            break


def get_vids(ac, disable_comment=False):
    vids = ac.Tik(no_proxy=True).get_self_videos().videos

    try:
        if not vids[0].is_available:
            print(False)
        else:
            print(True)
            if disable_comment:
                print(ac.Tik().disable_comment(vids[0].id))
            ac.close_browser()
    except IndexError:
        return False
    return vids

def set_url(ac, url, login_flow=True, comment=None):
    error_counter = 0
    ac.set('data.url', url).save()
    while True:
        try:
            tk=login(ac, force_login_flow=login_flow)
            r = tk.set_url(url)
            if r.user.bio_url:
                print(r.user.bio_url)
                if comment:
                    CommentScheduleModel(account_id=ac.get('id')).enable()
                return
            print('%s failed to add url: %s' % (ac.get('username'), url))
            return
        except (requests.exceptions.RequestException, requests.exceptions.ProxyError) as e:
            error_counter += 1
            if error_counter >= 3:
                print('%s -> %s: requests failed: %s' % (ac.get('username'), url, e))
                break
            set_new_proxy(ac, True) 
        except Exception as e:
            print('%s -> %s: failed to add url:: %s' % (ac.get('username'), url, e))
            if comment:
                CommentScheduleModel(account_id=ac.get('id')).disable()
            break
       

def set_dp(ac, img_url='img/gen/{}.jpg'.format(random.randint(0, 99))):
    error_counter = 0
    while True:
        try:
            tk = login(ac, login_flow=False)
            print(tk.profile_image(img_url))
            break
        except (requests.exceptions.RequestException, requests.exceptions.ProxyError) as e:
            error_counter += 1
            if error_counter >= 3:
                print('%s: requests failed: %s' % (ac.get('username'), e))
                break
            set_new_proxy(ac, True) 
        except Exception as e:
            print('%s: failed to sept dp:: %s' % (ac.get('username'), e))
            break

def set_bio(ac):
    error_counter = 0
    while True:
        try:
            tk = login(ac, login_flow=False)
            print(tk.set_bio(rand_bio_2()))
            break
        except (requests.exceptions.RequestException, requests.exceptions.ProxyError) as e:
            error_counter += 1
            if error_counter >= 3:
                print('%s: requests failed: %s' % (ac.get('username'), e))
                break
            set_new_proxy(ac, True) 
        except Exception as e:
            print('%s: failed to sept dp:: %s' % (ac.get('username'), e))
            break

def rand_bio(url='free4tiktok.com', is_url=True):
    link = [
        f'📲 {url} 📌', f'👉 {url} 👈', 
        f'👉👉 {url} 👈👈', f'💥 {url} 📌'
    ]
    a1 = ['🌐 Go to -: ', '🌐 Visit : ', '🌐 Link -: ', '🌐 Website : ', '🌐 Web -: ', '🌐 URL : ']
    a2 = ['GO TO ', 'VISIT ', 'CHECK OUT ']
    a3 = ['LINK BELOW 💥', 'WEBSITE BELOW 💥']

    a4 = ['👇','👇🏻','👇🏼','👇🏽','👇🏾','👇🏿','⬇️']
    bio = ''
    bio = '{} {} FREE {}+ TIKTOK FOLLOWERS\n'.format(
        random.choice(('GET', 'RECEIVE')), 
        random.choice(('💯', '', '100%')),
        random.choice(('10K', '5K', '1K', '2K', '3K', '4K'))
    )
    if is_url:
        bio += random.choice(a2) + random.choice(a3) + '\n👇👇👇'
    else:
        bio += random.choice(a1) + random.choice(link)
    bio += random.choice(a4) * random.randrange(1, 5)
    return bio

def rand_bio_1():
    a4 = ['👇','👇🏻','👇🏼','👇🏽','👇🏾','👇🏿','⬇️']
    return random.choice(a4) * random.randrange(1, 5)

def rand_bio_2():
    bio = '{} {} {} {}K {} {}\n'.format(
        random.choice(('GET', 'RECEIVE', 'GAIN', 'CLAIM', 'REDEEM')), 
        random.choice(('💯', '', '100%', '')),
        random.choice(('FRE3', '🆓', 'FR33')),
        random.choice(('10', '5', '1', '2', '3', '4', '🔟', '5️⃣', '1️⃣', '2️⃣', '3️⃣', '4️⃣')),
        random.choice(('T❗️KT⭕K', 'T❗️K T⭕K', 'T❗️K T🔴K', 'TiKT⭕K', 'TIK T⭕K', 'TIK T🔴K', 'Tℹ️KT⭕K', 'Tℹ️K T⭕K', 'Tℹ️K T🔴K')),   # 'TIKTOK', 'TIK TOK'
        random.choice(('F⭕LL⭕WERS', 'F🔴LL🔴WERS', 'F🅰️NS'))    # 'FOLLOWERS', 'FANS'
    )
    return  bio + '\n' + rand_bio_1()
    
def adult_bio():
    # bio = random.choice(('💄', '👄', '❤️', '❣️', '💓', '💗', '💕'))
    bio = 'GET 💯 FREE ACCESS TO \nMY PREMIUM ONLYFANS\n'
    bio += random.choice(('💄💄', '👄', '❤️❤️', '❣️❣️', '💓💓', '💗💗', '💕💕')) 
    bio += ' ' + random.choice(('CLICK', 'VISIT', 'GO TO'))
    bio += ' ' + random.choice(('WEBSITE', 'LINK')) + ' BELOW\n'
    bio += '👇👇👇'
    return bio

def random_img():
    path = 'img'
    return f'{path}\\{random.choice(os.listdir(path))}'

def rand_vid(path='D:\\Bots\\Tiktok_Extra\\processed_vids'):
    return f'{path}\\{random.choice(os.listdir(path))}'

video_list = []
video_source = None

def rand_video(path='D:\\Bots\\Tiktok_Extra\\videos'):
    global video_source, video_list
    if not video_source:
        video_source = f'{path}\\{random.choice(os.listdir(path))}'
        video_list.clear()

    vids = os.listdir(video_source)
    while True:
        if not vids:
            raise TypeError('Videos empty')

        vid = f'{video_source}\\{random.choice(vids)}'
        if vid not in video_list:
            video_list.append(vid)
            return vid

        vids.remove(vid.split('\\')[-1])
        
def clear():
    global video_source
    video_source = None


def move_dirs(cur_dir, dest, L):
	if not os.path.isdir(cur_dir):
		print('invalid cur dir')
		return

	if not os.path.isabs(dest):
		dest = os.path.join(cur_dir, dest)

	if not os.path.isdir(dest):
		os.makedirs(dest)

	for sub_dir in L:
		dir_to_move = os.path.join(cur_dir, sub_dir)
		if os.path.isdir(dir_to_move):
			shutil.move(dir_to_move, dest)
		else:
			print(dir_to_move)

def copy_dirs(cur_dir, dest, L=None):
    if not os.path.isdir(cur_dir):
        print('invalid cur dir')
        return

    if not os.path.isabs(dest):
        dest = os.path.join(cur_dir, dest)

    if not os.path.isdir(dest):
        os.makedirs(dest)

    if not L:
        for folder in os.listdir(cur_dir):
            base_f = os.path.join(cur_dir, folder)
            if os.path.isdir(base_f):
                base_f_copy = os.path.join(dest, folder)
                if not os.path.isdir(base_f_copy):
                    os.makedirs(base_f_copy)
                
                for item in os.listdir(base_f):
                    if os.path.isfile(os.path.join(base_f, item)):
                        shutil.copy(os.path.join(base_f, item), base_f_copy)
    else:
        for sub_dir in L:
            base_f = os.path.join(cur_dir, sub_dir.strip())
            if os.path.isdir(base_f):
                base_f_copy = os.path.join(dest, sub_dir.strip())
                if not os.path.isdir(base_f_copy):
                    os.makedirs(base_f_copy)
                
                for item in os.listdir(base_f):
                    if os.path.isfile(os.path.join(base_f, item)):
                        shutil.copy(os.path.join(base_f, item), base_f_copy)

def del_dirs(cur_dir, L):
    for item in L:
        dest = os.path.join(cur_dir, item)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        else:
            print(f'{item} does not exist')


def download_vids(ac=None, username=None, url=None, max_download=200):
    if not username and not url:
        raise TypeError('Provide username or video url')

    _, sec_id = username_to_id(username)

    ac = AccountModel(username='yearspoint.415')
    Tik = login(ac, no_proxy=True)

    user_info = Tik.get_user_info(sec_id)
    print('%s - video count: %s' % (username, user_info.user.video_count))


    parent_path = os.path.abspath('videos')
    if not os.path.isdir(parent_path):
        os.makedirs(parent_path)
    
    path = os.path.join(parent_path, username)
    if not os.path.isdir(path):
        os.makedirs(path)

    video_list = os.listdir(path)

    max_cursor = 0
    count = 20
    has_more = True
    counter = 0

    while has_more and counter < max_download:
        resp = Tik.get_user_videos(sec_id, max_cursor=max_cursor, count=count)
        
        for video in resp.videos:
            counter += 1
            file_name = username + '_' + video.id + '.mp4'
            if file_name in video_list:
                print('%s already exist' %file_name)
                continue
            
            url = 'https://www.tiktok.com/@' + username + '/video/' + video.id
            print('%s. downloading... %s' % (counter, url))
            
            r = requests.get(video.url, timeout=5)
            open(os.path.join(path, file_name), 'wb').write(r.content)

        max_cursor = resp.max_cursor
        has_more = resp.has_more

def check_account_info(Account, folder=None, no_proxy=False, check_videos=False, console_log=True):
    print('{:>5}checking.. {}'.format('', Account.get('username')))

    try:
        Tik = login(Account, folder=folder, login_flow=False, no_proxy=no_proxy)
    except Exception as e:
        print('%s: failed to login. %s' %(Account.get('username'), e))
        return
    

    result = ''

    error_counter = 0
    while True:
        try:
            info = Tik.get_self_info()
            break
        except (requests.exceptions.RequestException, requests.exceptions.ProxyError) as e:
            error_counter += 1
            if error_counter >= 3:
                if console_log:
                    print('%s. %s: failed to get info. request error %s' %(Account.get('id'), Account.get('username'), e))
                result += f'{Account.get("username")} failed to get info. request error -> {str(e)}\n'
                return
            set_new_proxy(Account, True)
        except Exception as e:
            if console_log:
                print('%s. %s: failed to get info. %s' %(Account.get('id'), Account.get('username'), e))
            result += f'{Account.get("username")} failed to get info. -> {str(e)}\n'
            return
    
    if 'no bio yet' in info.user.bio.strip().lower() or len(info.user.bio) <= 5:
        if console_log:
            print('{:>5}{:>5}: has no bio.'.format('', Account.get('username')))

        # result += f'{Account.get("username")} no bio\n'
        try:
            Tik.set_bio(rand_bio_2())
        except Exception as e:
            if console_log:
                print('%s. %s: failed to set bio. %s' %(Account.get('id'), Account.get('username'), e))
            result += f'{Account.get("username")} failed to set bio -> {str(e)}\n'
    
    if not info.user.bio_url:
        if console_log:
            print('{:>5}{:>5}. {}: has no url.'.format('', Account.get('id'), Account.get('username')))

        result += f'{Account.get("username")} has no url.\n'
        CommentScheduleModel(account_id=Account.get('id')).disable()
    else:
        # Account.set('data.url', info.user.bio_url).save()
        if info.user.bio_url != Account.get('data.url'):
            CommentScheduleModel(account_id=Account.get('id')).disable()
            if console_log:
                print('{:>5}{:>5}. {}: has no url. (profile url different for data.url)'.format('', Account.get('id'), Account.get('username')))

            result += f'{Account.get("username")} has no url. (profile url different for data.url)\n'
        # else:
        #     CommentScheduleModel(account_id=Account.get('id')).enable()
        #     print('{:>5}{:>5}: has url.'.format('', Account.get('username')))

    if '1594805258216454' in info.user.avatar_url:
        if console_log:
            print('{:>5}{:>5}. {}: has no profile image.'.format('', Account.get('id'), Account.get('username')))
        result += f'{Account.get("username")} has no profile image.\n'
    
    if info.user.username != Account.get('username').lower():
        result += f'{Account.get("username")} has changed to {info.user.username}\n'
    
    # if info.user.nickname.startswith('user') or len(info.user.nickname) < 10:
    #     print('{:>5}{:>5}: has no nickname.'.format('', Account.get('username')))
    #     result += f'{Account.get("username")} no nickname\n'
    #     Account.set_nickname()
    
    if check_videos:
        try:
            videos = Tik.get_self_videos().videos[:3]
        except Exception:
            print('{:>5}{:>5}: failed to get videos: %s'.format('', Account.get('username')))
            result += f'{Account.get("username")} failed to get video\n'
        else:
            video_available = False
            for vid in videos:
                if vid.is_available:
                    video_available = True
                    break
            if not video_available:
                print('{:>5}{:>5}: has no video.'.format('', Account.get('username')))
                result += f'{Account.get("username")} no video\n'

    return result

def check_accounts_info(accs=None, tags=None, folder=None, no_proxy=False, check_videos=False, console_log=True):
    # return
    if accs:
        if type(accs) is not list:
            raise TypeError('accs must be list')
    else:
        if tags:
            accs = AccountsModel().where('login_required', '=', 0).where('tags', 'like', f'%{tags}%').fetch_data()
        else:
            accs = AccountsModel().where('login_required', '=', 0).fetch_data()
    
    if not accs:
        print('Accounts empty')
        return
    print('Accounts: %s' %len(accs))
    
    result = ''
    for i, ac in enumerate(accs, 1):
        print('%s. https://www.tiktok.com/@%s' %(i, ac.get('username')))
        res = check_account_info(ac, folder=None, no_proxy=no_proxy, check_videos=check_videos, console_log=console_log)
        if res:
            result += '%s. https://www.tiktok.com/@%s\n' %(i, ac.get('username'))
            result += res
    
    if  result:
        with open('accounts_check.txt', 'w') as f:
            f.write(result)
            print('results saved in accounts_check.txt')
    else:
        print('check_accounts_info exiting. no results')


def upload_video(Account, url='https://a89627fcd59f.ngrok.io'):
    video_url = f'http://755d09ac854a.ngrok.io/v/{str(random.randrange(1, 140)).zfill(3)}.mp4'
    api_url = f'{url}/upload'

    api_data = {
       'title': '#foryoupage',
       'fileurl': video_url,
       'noComment': 1,
    }

    tk = login(Account, login_flow=False)
    api_data['sessionid'] = tk.settings.get('session_key')

    failed_counter = 0
    while True:
        try:
            resp = requests.post(api_url, data=api_data, timeout=120)
            break
        except Exception as e:
            failed_counter += 1
            if failed_counter >= 3:
                raise
            time.sleep(5)
            print('%s video upload error (%s): %s' %(Account.get('username'), failed_counter, e))

    return resp.text

def upload_videos(accs, url='https://0c5d77928936.ngrok.io'):
    index = 0
    while True:
        command = input('> ').strip()

        if command in ('s', 'stop') or index >= len(accs):
            break
    
        if command in ('n', 'next', 'r', 'repeat'):
            if command in ('r', 'repeat'):
                index = max(0, index - 1)

            video_url = f'https://755d09ac854a.ngrok.io/v/{str(random.randrange(1, 140)).zfill(3)}.mp4'
            api_url = f'{url}/upload'

            api_data = {
            'title': '#foryoupage',
            'fileurl': video_url,
            'noComment': 1,
            }
            ac = AccountModel(username=accs[index])
            tk = login(ac, login_flow=False)
            api_data['sessionid'] = tk.settings.get('session_key')

            print('%s. %s -> %s : Opening browser' %(index, tk.settings.get('session_key'), ac.get('username')))
            for _ in range(2):
                try:
                    requests.post(api_url, data=api_data, timeout=40)
                except Exception as e:
                    time.sleep(2)
                    print('%s video upload error: %s' %(ac.get('username'), e))
            
            index += 1
        else:
            print('enter valid command')
    
    print('upload_videos exiting.. ')


def delete_logs():
    def execute(sql, params=None):
        error_counter = 0
        while True:
            try:
                with Database('tiktokbot.db') as db:
                    db.execute(sql, params)
                break
            except OperationalError as e:
                error_counter += 1
                print('%s. %s' %(error_counter, e))
                if error_counter >= 10:
                    raise
                time.sleep(random.randint(2, 3))
    
    # delete unfollowed
    sql = 'delete from follow_log where status=?'
    execute(sql, ('unfollowed', ))

    # delete fail
    sql = 'delete from follow_log where status=?'
    execute(sql, ('fail', ))

    # delete video_like log
    sql = 'delete from video_like_log'
    execute(sql)

    # delete comment log
    sql = 'delete from comment_log'
    execute(sql)
    
    print('Done!')


dummy_accs = [
    # ('username', 'user_id', 'sec_id', 'count')
    ('user16061996178887', '6905306451789841414', 'MS4wLjABAAAAseiUclvQ-0e6TsH7bw9i9mhhD2tRtOBkG0oWJPZW8cS6197ym0fV6ElAdlveYtW8', 0),
    ('user1996359482249', '6905309718647702533', 'MS4wLjABAAAAKFpcOgFhmZFVHOvMvsXJHKQXwuANYRqrWPqUs3ary1TLIFZTojV_GiaE_X3pYLEE', 0),
    ('user8008239407682', '6905309749224670214', 'MS4wLjABAAAAaXxbjkOYPi8LVPbATfH2T5ew2Mh8VNL5DcOsgn-ZJHqkjgAjdKpklNmuF_US_CIs', 0),
    ('user218850130757', '6905309637916574726', 'MS4wLjABAAAAIA7_HQfNY41318mm_Ppyq4lDWArEPV5lwt0jcdD6aeEQ87sr41IPse_H4i784FH5', 0),
    ('user6449236564966', '6905309718647751685', 'MS4wLjABAAAApcLqLKovuNMktuPCc4D9qYpBQUrhQbeK9mOORXbkL3oMncDwVjgzgoJ3sjwSYIj5', 0),
    ('user6930097206793', '6905309721416532997', 'MS4wLjABAAAAwMX3l9cTYV_m_pF8c36DeHAl456plY2YFvl--ZfCAvazNEs2Rn1Pbbiq-qswxeyf', 0),
    ('user908246774071', '6905312636805792774', 'MS4wLjABAAAALQlvuO8u4qkY6sLnVDw7w6yH8h8oOklLr9p-xOrp3Wxf8_R7NYU8ox37laLPo0VJ', 0),
    ('user5093769504190', '6905312571038696454', 'MS4wLjABAAAAZXBLNHN-2hVpks165Axxe2sFC0tc8cRxafzsX8DBzdtGDQzQedu2bbCx-9GlUtBi', 0),
    ('user8783952507467', '6905312571038893062', 'MS4wLjABAAAAZGo5itF2bmp-o7JlNklJuYonOT1Y-7RQKpDV6NlmM7-AtqFPNJ8P0V0Dor1v45r3', 0),
    ('user5814986897029', '6905312571039024134', 'MS4wLjABAAAAHF2Ddw6B1rjoYTQB7M0miNjMVXKR6nw6NrR3IWumJhLI3aajgfbqRoknNamfmCUI', 0),
    ('user9310174452704', '6905314957496353797', 'MS4wLjABAAAA5xOE7M-7kZNWCtcXTeasU0tfzOrQgpbc8FL_n7R_tMxk6HWSBbcFj4gXqvS7QocP', 0),
    ('user437236376169', '6905315046710412293', 'MS4wLjABAAAA1J9J7LvyuWIOX3pjbLyGmP40HCvC3dcTj1sTtrkm4XJn_EPUTlBd5y-s4MOe3UAc', 0),
    ('user803679324164', '6905314957496501253', 'MS4wLjABAAAA_7dQUM52TSxxjUntpNGdpzMEkFBRQOrD4BvRFn875uygpfY35w-SS7PvUZ8_2YzH', 0),
    ('user9002158552528', '6905315682762654725', 'MS4wLjABAAAAg8sK7zETFpyW5OPALI22Zotlp2juCLbmsvZuAuJmLD0zvWjCbf-kwJUVVMcGew0q', 0),
    ('user4967305386438', '6905315769006425094', 'MS4wLjABAAAAXpmJCjUZGTwdCXXu0FnK5IUZ7Z2u0dzQKFTZgqyyDbkRvbI54PfQBlS6JFOSi4Sr', 0),
    ('user5192711141145', '6905316621524272133', 'MS4wLjABAAAAGw_adkd1iKcJhM2tQqle_OdeJj38jzlysSF_yaeBG0p0-QbPMVP8RJPEHmY490Rw', 0),
    ('user95190631097', '6905316591132967942', 'MS4wLjABAAAAdmZhujnrSfzXhmrLNNyEYN4_A6h-oe48zmeNy60sStOu6wSaOhdFiDb79xL77sNk', 0),
    ('user7984784048541', '6905316678591972357', 'MS4wLjABAAAAW0wjVD371k7JnCbRVjuZbwHAOVSCOMJEsM6q3rzbaHBljaTYWOSUKk-4DNQcTjPS', 0),
    ('user1089786876239', '6905316735432639493', 'MS4wLjABAAAAZ6iEaHpSzyS03BnDfXX1TwsOlUObM-rSUlIg8_2km0SCpTJjTR9t5BAsNl92hOHT', 0),
    ('user2381532645610', '6905316619633230853', 'MS4wLjABAAAAk--Z3wIuvCkUnHMxy56yXMTQdFD7aAKa_OC1f_3CAWDDVeGAgIbiLx4kNa4w0bYV', 0),
    ('user4904634060769', '6905319113042035717', 'MS4wLjABAAAAV8e2Plg6erUeK-JoFkXFxxaJRpwXZCWf08eXOkmLVInJgc5ZPIp3juAUf2LtYOW3', 0),
    ('user3861497295550', '6905319224219059205', 'MS4wLjABAAAA0jRa1Gb2_JyURQxjnzLTO9gOC010LjqkwpU-kvQbXv52MPCANWrhL4uSzHmSiTnq', 0),
    ('user3374756483867', '6905319173312988165', 'MS4wLjABAAAA5qlE5fwAnJGLeiC8eYOCBnzr0Iq2kjCJcpXhtP1oqKGECe2UllK1Bqhx5xlOT30c', 0),
    ('user5399910136619', '6905319113822340102', 'MS4wLjABAAAAwXIxS7QQ-QfDCPSK5RfRv9DzRH_ArFkaLh4zqsXkTyjwP_mV2Y2be7-rhOGeChNf', 0),
    ('user8479378734655', '6905319199011996678', 'MS4wLjABAAAAMXYF1n1a1mOONRfUMHiwfCWBJujNRFWH3rgZqNbSdmLnsbus5CtFGRKU1HMy3wmV', 0),
    ('user9368149156705', '6905319198102406149', 'MS4wLjABAAAADyntGfEvAROrOU_Nz5CKknp6l75T-VRKFdh6g_PXvfrIlLmjDZm70DC87FgnDWbX', 0),
    ('user5126038995870', '6905321587945587718', 'MS4wLjABAAAADtXy2TXHFmsMLE5jrKR89HKJVb0r6hkiXzJtDcuiyG23sJouPMIMpr8bLwBXrN2C', 0),
    ('user4665240690871', '6905321591866393606', 'MS4wLjABAAAADVJv5l-AT-FuXXilcOD4Vwk3UNDIYJRf5RyuJSCsa95WHCb2MmxbLCR3pg5xI8q7', 0),
    ('user6905554311166', '6905321591866262534', 'MS4wLjABAAAARv24eqCHpsrK9HRQ2GrZhFfP_y6oOu7O_oSh3XctBApjy53Chb1h-M1lYK5QG3EG', 0),
    ('user983220791271', '6905321540222682118', 'MS4wLjABAAAAaCztfqLwiK5BdeGFt7-lnOA0MmIp8lgwSDAQGrvrf0kb_ONgJ__wE-BZxWhnJW3G', 0),
    ('user1517501206414', '6905322550399943686', 'MS4wLjABAAAA18jUDwG-n2Inz04nzicFYNpm-qzaiODhTtryEqLNPk-v_WUo_ReL9_cdNxpjtYTp', 0),
    ('user1879503105664', '6905323174826460166', 'MS4wLjABAAAAKsZxwyhA58pXLi_YEQ8datl17DLkA68c5wziy-eybU9kELKBpfWoV4yv6Si5HrdN', 0),
    ('user6203680415086', '6905323141930157061', 'MS4wLjABAAAA_O-FsVrdJuXdDj5_EDtIXh0pzi_Wv7HjcTjAiy4LBlL5VWk8_XhL311Ysw67KrmL', 0),
    ('user4943228878192', '6905323012560684037', 'MS4wLjABAAAAz-vg3TsAvKBOg7BqScMW6NTN5Wg0nZ61tT7Ja2q_5PKZwltMHf1IOwEzxeK6_nfX', 0),
    ('user1295337374117', '6905324571787822086', 'MS4wLjABAAAAnwMSssYYk5jturxZBLYjK_xEC0hXtFGfh71BAOE9vI5EuXNPQ4qa3xSH3LDVdacj', 0),
    ('user2575661403347', '6905325379817948165', 'MS4wLjABAAAA8TnF9VrypJqK7q_PAKNpkHPeiriagB6OVm33BnGmNvCifTF-ckeWxBif7mcz4PWH', 0),
    ('user2111995695487', '6905325273920832518', 'MS4wLjABAAAANCr_BShFdXJW01GrCPFt6FUPvKF2E2G-DKzMSKTkFXqd3_C-obvPWsFW6fBsEvD1', 0),
    ('user5430849506696', '6905325273920816134', 'MS4wLjABAAAAAjldkOizEWRcTZe0VSFn35eY1KPnvYFQoUi0FExy3S7yR0fCnQc2XFhrpRH13TtU', 0),
    ('user39590635424442', '6905326100445004806', 'MS4wLjABAAAAXYTWAXTBFZnCC1I4QK5RZywn5_lmdR6YG0-e80XPzEv-LKzmQqat_88h-RPYzZyl', 0),
    ('user247517856913', '6905326119810515974', 'MS4wLjABAAAABWLqGpoVwdojZ_nENOASYkTpachS0HkXyEP4C8ZCrNs8agIv3eMNeKMlwKMXMGto', 0),
    ('user318955614556', '6905327017115714565', 'MS4wLjABAAAA5p4hgpdw8gfk3etzJ6lzLSbp-nrA9XoIsgcW69wPnzDC09ZmYeoRtADvBgJS3egp', 0),
    ('user9826783940742', '6905327142810092549', 'MS4wLjABAAAAvWglLktVynfA91bGZhNnKat_PUBe5-OGNqth9pVpL1pGOiC6rqm2QPUFU_jrDTiF', 0),
    ('user9533015655726', '6905344550878610437', 'MS4wLjABAAAAjegmsckK0fBQecnZe4swCn-jlq3gS18SD6Y_XTw8qLgG159EraJMiExZtJQSFh8H', 0),
    ('user7513794297421', '6905344571560346629', 'MS4wLjABAAAAie8eKfWlAZ3bL5V55JWzJxm7I4U1aE6wMRVbL-7HlOwTYc0VhotOS53UzZpanmjs', 0),
    ('user5289244720627', '6905345316067230726', 'MS4wLjABAAAAuAD3orKem9JAGpueDEwEn0rwGUlSuDbEqQ9zObwVut8klATnGQafYPmjmlUEHscA', 0),
    ('user9251180155743', '6905345237200634885', 'MS4wLjABAAAAQxBBfNAssdomGJt3dIkD8BV1W8O8DB4mTeuIXX436tg6-euc2SHDStGNnyMgVyNJ', 0),
    ('user5773243462150', '6905346785264583686', 'MS4wLjABAAAAgG-KiRcjyN2DKPKlgUfasW--iHPok2hsB_Zvpp9zlTIASXB3Xqt38xvOAxP8qmF3', 0),
    ('user3624081410003', '6905346808231838726', 'MS4wLjABAAAAlJkLXM78ajRy71XZf7D4t5du901iMxweIh3qSk-23jaqc3bmW_NCzY2tglI3-COJ', 0),
    ('user8458409207228', '6905346765579994117', 'MS4wLjABAAAAjUHyu0c0gfijSJEmFjTPliAoxpjirvn5gVBZ0EnMzVZGcJs_4pyaGQSH6OyZcSfL', 0),
    ('user7743622383394', '6905346765580715013', 'MS4wLjABAAAADoE13ZwCHtpCzryLpiedXpbrWQH8GrrDvzv2b9EogA3vth5e5sQhlSsCSClg-hea', 0),
    ('user6491223745119', '6905347430808683525', 'MS4wLjABAAAAiv0dI9pOJaEqiUfPl4rk8jbyhqdL8KFr9C2RE6fILNWyLhepH3z62On7jdS_soK_', 0),
    ('user3466236807628', '6905347405471056901', 'MS4wLjABAAAAdmoebKpydAAJpuBVecHPsVz4K2mLI5PhFCG7SgM-v0g8-ZYA8sGSBOSfcxyoM0jK', 0),
    ('user7878434693304', '6905347773680944133', 'MS4wLjABAAAA7u33SFNpp3M_FrJv3E9Enze82YOb4j0DklaEbKl-0m2EISnSR-2-yeNiE09IQER7', 0),
    ('user1917051580186', '6905348389513626630', 'MS4wLjABAAAAYnURaJQ8AfkS9MM_eFq0TbjaUv5VZLOlVSilRpg7HMu--iw0PuMc-XAJWMJeVOs7', 0),
    ('user6042411188273', '6905348457201239045', 'MS4wLjABAAAAXEJy05ZxI-5pYyDzxOFTZBTNsdoF9MGO7TeHiN0bpI1bGFrE_6TY_9ITxDxO89Yk', 0),
    ('user5210372193958', '6905348499634848774', 'MS4wLjABAAAAbuf0eIBt7MFPZCKMZis52gLbO-AIFdwje6wM6NWKVTA0YB5BoGeVZIsE_-VmCbMT', 0),
    ('user8171752757580', '6905348457201632261', 'MS4wLjABAAAAvgy3t59snWDCS9kiT01fs3CcuxGsLS_mRPbJu8jPr-_ODqtt2zV9wqjcwFJk4Vkk', 0),
    ('user1454177936115', '6905349048224646150', 'MS4wLjABAAAAdzP2XQ0Noe_O_UCqw_N3-xEDg3CN2zpWf9QXo7V4Jx2Ay8yNWNLd8Z_xrBqFdKD9', 0),
    ('user9866670674231', '6905350623677236229', 'MS4wLjABAAAAW2vh28u9uLaEqsFoExJ9pqpl5jL1OwE9r4PV8UEnTjvS3Iq6iTE80v_t3PSBwfPD', 0),
    ('user4002445145528', '6905350626991178758', 'MS4wLjABAAAA8i-G8NPQ2ZGHBVokSWqJU4Jn03GbvhJkvxOK3OtP-ASkmvBRFNqJ0TtXuzlhIgmd', 0),
    ('user258643493000', '6905350689192887301', 'MS4wLjABAAAAaZrTlcJyd7uC5vSVWziHx3OVOx0hDbb2B2nU6EjZ0IxL3sAPN1TLic0DqZFAlalk', 0),
    ('user7853457664040', '6905350619038729221', 'MS4wLjABAAAA8GA5Y8RRn1FYuhMW-hwwdqPEn_JfN4dQfnAVp0EQTMcaeANKkMOfxCvNq892PtAt', 0),
    ('user3917916893769', '6905350660594828293', 'MS4wLjABAAAAvEdT_3Gsrj8cyC9G66OB-gs0qlApnGoC0Cgovmj3lAkW_Uj7RTd5T0SbtVum0emW', 0),
    ('user4140610253390', '6905350706547819525', 'MS4wLjABAAAAq0YlCNCFBar7qIZzVJUeEyCAaXb_CIxD7fWBvJorHssDPkoP2ceGF7OC86_vpwaA', 0),
    ('user1983108568025', '6905351317607662597', 'MS4wLjABAAAATI6U5GO6Ro0q63-X3bChJ069BXhs-_05PXWQxG9l9vNIUF72VWPnJnxmPTDMQc0e', 0),
    ('user830906773', '6905355653158847493', 'MS4wLjABAAAAfxbVn8wUnkRSx68gGfucBpZewcYsQh4a30zFnFn8TAK5qvREEQEwpVn_Em-n_ZlY', 0),
    ('user7067673605823', '6905355637590508550', 'MS4wLjABAAAAJsi22lX2czLAE9hHFJUXWmGlRPyhNhlV9UHXRe697DjbjqNWLxEZu29eW3Q_ZGwg', 0),
    ('user9564789125013', '6905355817777923077', 'MS4wLjABAAAAAUxx7EVNZ6wV4qVmznSNLIHKCkxNF9qR-B4Q0wAKwW-jIx9xekXnDdLIpGx9YsIz', 0),
    ('user5340956918989', '6905356495040218117', 'MS4wLjABAAAATGGo-fB16hbOdFCoTT7gT1tQKRZdcwkBpIijCQjj7AoCCF1iJYAjL_EvNy96XP_3', 0),
    ('user3412677753849', '6905356681422406662', 'MS4wLjABAAAAFTF8Z3oaEtHe7YoFyj2DBUvhtA75yvuTDBfU3HvKyoC-fj1OLjOAK_ROp3Cwvdsz', 0),
    ('user7163767514807', '6905357326628439046', 'MS4wLjABAAAAB4Au3P7aAwX5euI6oe0iXkdVWqkDYrpblLvJEQ-Y3GFuKKNlC3Zp3uiT4kkmWWCc', 0),
    ('user792890761090', '6905358022353601542', 'MS4wLjABAAAAMFxczcSGjFuJEqwh_EquOV7_pSgOUP9kcX5FPgbGorPXvT8Im4auGRsEDdBugiAo', 0),
    ('user1405466558382', '6905357962556212229', 'MS4wLjABAAAAyWyDMhvWHOyDYZFfwQumE2axMAEkSnXfSgNHrDxiKBM0-9W808gRXgUzGdJCO-t2', 0),
    ('user11864727765137', '6905357982843716613', 'MS4wLjABAAAAXpoS48hTg4_en8WmbHTJ1iOvMqgYMsJLlCVfTNgZY3GDEWLMS9DiPQaUf2yz8py2', 0),
    ('user2758515987054', '6905357909698479110', 'MS4wLjABAAAAUA568LyvoWf__-L0jSRMxbXMDfrNB-ngQdvsWLGehNrXVgEW5KRshDXJRdbpQ8_g', 0),
    ('user5680404049987', '6905357926354863109', 'MS4wLjABAAAAeN5WWY41TRHvvs6-TnFW8W8gqxvi9M0wqYMaScJTZqD1hYtBs0n3V7LUC5A1TkY3', 0),
    ('user8510922631510', '6905357909698282502', 'MS4wLjABAAAAupR1kkxnce1vH91V9r9XL05YLXD_XurkO_kTsJVrCTpBIlw8XcyXPr1lLx1M4lN7', 0),
    ('user9712931635270', '6905360215979361285', 'MS4wLjABAAAAg2ZOZJw9xrt64K55fQPpU7dKx00IiX1HxJRtGV_O3yDPxXWKHijG2CTQQK1Zp77i', 0),
    ('user1614120094473', '6905360410025001989', 'MS4wLjABAAAACbVefSeiXep_OeATLu7C2FtGLU43i2pOv5Vkx_-jf7Oemmkz8x9R8PWzLsXDf6k_', 0),
    ('user3809789269441', '6905360494447199238', 'MS4wLjABAAAADV2-xFvP4Vxj93fHaPjZVcXRA0PNOxF6diP6ksAdXXVk1e_WYKqZUpUvWEJmTN_i', 0),
    ('user7412575008190', '6905361160930395142', 'MS4wLjABAAAAIRGYo5E3B9SSKdAGAhAp3iVg41o6JUWpjuGhnP83qT3hzu2JWDjPjNJqmFKfy9eF', 0),
    ('user1889229607190', '6905362464034325509', 'MS4wLjABAAAATUEu8mjOSbD5Kvkdd0E_8mXAeH8TrBYsF07uhnhk9OLGUbk2F0ca3A5B3BuKWlMs', 0),
    ('user3333876719862', '6905362960748643334', 'MS4wLjABAAAA1qCWkM3aH_nyn7XVFQ7daL2LkxL5Xdf3nrW1xWi_Z1NaajdzuoWRhZJJHcW_0gNm', 0),
    ('user5410210325780', '6905365058226930693', 'MS4wLjABAAAASKSABpCZdypyj3kLIm05_4qDjeIN1ttOAK6-ufmf9EInbhFqC_IxMBrWQKdknBub', 0),
    ('user6309012383020', '6905365096022017029', 'MS4wLjABAAAA0aM6kXMV4jzbmUzunTbdgvBtiEe2f-mHBwOMr3W_Oif6HvWWA-mmfE6b7YExtHxd', 0),
    ('user3016518562217', '6905365826988934149', 'MS4wLjABAAAAnCs2mqU5LehNu0NcR38rxQ77VmYE6-rmnivblgpgtzrGlzP8emhovLdDJeOaXNUD', 0),
    ('user4485693363677', '6905365729437762565', 'MS4wLjABAAAAItjzrwF_D6YPzqYbCFeXS_B9girWpZ5MAiIPAhLyelzqtPScjZuvefg4-OraZbS2', 0),
    ('user2786899138412', '6905365752308614149', 'MS4wLjABAAAAEnyPcatTKUeYa4lV0wxsN2foMwqn2ybabprxJWODQjUBTaeaXtx45Su0OQq5IBgD', 0),
    ('user3494554301773', '6905367194588709893', 'MS4wLjABAAAA6wLJWKSCK31e21ifsBNLEjcAe4qTODOYnpZjgPFFhKNwuWBGC5ykU6Q45Sq1qeNs', 0),
    ('user2212011513747', '6905367232643204101', 'MS4wLjABAAAA_ZBCbP5ExxC_prnVd4ehDcOjisUQQhAvSspeZVDWOOUtO0eoxN2_-Kxz3_UeOjpA', 0),
    ('user9453525840432', '6905367211160339461', 'MS4wLjABAAAA5EKxHUaxjrdtJUYLnnC2fCUOWivaIe-DDaxM-uZ97PCdvLlqaLgJsZRD43g7KosP', 0),
    ('user9383267406522', '6905367266167555077', 'MS4wLjABAAAAgHEFmtoh5LJqQwN6fduwhYYj_zRl3vVBfrwF8nfWMP54mHxeirWjROvhBwADForR', 0),
    ('user92218856326197', '6905367176778793989', 'MS4wLjABAAAA4jrBiF1RpnNa61LTQBwDKtj4bz9WNeCQaf77rSxq8y_4YV2eP2z7VGr_ZiirRqg1', 0),
    ('user7417961344841', '6905371693780059141', 'MS4wLjABAAAApJoWX7A_pDNOt2lWkPo33NxAKvxK9T9uwnBWPIHKlnDVHGJXyfCzk-X7nqYgqyPi', 0),
    ('user1320797590625', '6905371693780698117', 'MS4wLjABAAAAMyg9RAK7Mz9uhgV3vfyxIKAmeyg-5tozBAChTU9ymkCG5e_iz49htq6A11jeGM_Q', 0),
    ('user4324742419204', '6905371695595488261', 'MS4wLjABAAAAL6nGPzZqL3uXkFMe-fA8PT7DVgb9Q1U2ZvU5jVBH6983TVbrNPZMKe0l49BJ9Bq2', 0),
    ('user5712332604414', '6905371693780419589', 'MS4wLjABAAAAkD-Ndq9LTtBAbhLOXZGX-fEM4YaFUhnap3eUyGofooTLUHf-6WFw9irN_lDEKH7S', 0),
    ('user8255670539674', '6905372564283606022', 'MS4wLjABAAAAqOS2MMUAhdGSG60PQDbe3qUB2j52a0dNOQmqUzewdCzcxU5zQy7LoeRvBTK4JRNE', 0),
    ('user9388865992543', '6905373491340788741', 'MS4wLjABAAAADmgDuYVr56-UynFxv2KedF28Za0hL1wmyqf8Dq7Gn4e3S0_r5irJIgsIOHEik3qT', 0),
    ('user84331662635411', '6905373453999948805', 'MS4wLjABAAAAoIqOjJDMlv9xgbFJT6w7GU_ZOgR_PYCOgl7RKehcyO7xxsuG7AadJ59mFU-Rdhr3', 0),
    ('user2329272830829', '6905373452121293830', 'MS4wLjABAAAAW_M_9SVzzPpXTjduUKX0L7o75eVaKd39huK0F2px4UqF6ExB1Muy63_Yr3HKLyjb', 0),
    ('user7091740691033', '6905373429148713990', 'MS4wLjABAAAAG8dH2GIQodudXMnuNwwVkZHWpgh4sGswWYLT9R49p4ZnV-M0PJOU0lB3tsPp-LS2', 0),
    ('user1730450799221', '6905374945967850501', 'MS4wLjABAAAATvmqmo64ZSI6D8QBKx4PylxaOw7kSkCKjgLek6yO1FhPp3gtK81G6-O4ZIj5jGEM', 0),
    ('user4894964409018', '6905374971372225542', 'MS4wLjABAAAAFJWxfsOn-aQodmMQV0-hiLKd2skQ4HOPCStZD0WDF3O2MU7xc-5CIP458KKJWq3b', 0),
    ('user2028923696874', '6905374984815019014', 'MS4wLjABAAAA9t1CKdhT6cnvVjo8FrVjIysS2Sz6uAekHYj0kVAK9j1jJspRRhVEAcSHYFeMhZcQ', 0),
    ('user2360717202423', '6905375574614410246', 'MS4wLjABAAAA539KUyEZqtaB4pH4IZrbEVfBdiSD7QTQtWGOkCh_-lKIxXDr1z_XNy3cSB33oi2d', 0),
    ('user3497539327059', '6905378038268527622', 'MS4wLjABAAAAtTKIDvaFPauq-E22lV-0eWrpeKLBpYNrCylID2Tk77sQAD18UzNCm7-3RUVUfRm_', 0),
    ('user3441612512423', '6905378026532766725', 'MS4wLjABAAAANRFIdczsY_zVjlMu5VRPfXdTBDnULiA1x-YsaInJxKSYsMxvTM4qCgkF6_wII2A6', 0),
    ('user7746751388024', '6905378038269133830', 'MS4wLjABAAAAFtok9s4EIi_L9Re4doah685b_WRwdtngtmPR2fbRa7gA61-o9rNB_rems1OKGLWl', 0),
    ('user3357901200054', '6905378659307766790', 'MS4wLjABAAAAm1pOznr0mbKbSV60eEOQBocMbP0IMBCuJ_nyI-3YsHgv8cc04Hvmpm4zE-lLNTSf', 0),
    ('user9781029012663', '6905379607488906245', 'MS4wLjABAAAA0NAArwiyCKYxt79Cz8XJdnDue7Ethf-ToiuJfHSsO2lg8pSev01CXmYDarhw_eov', 0),
    ('user5382697551174', '6905379687440237573', 'MS4wLjABAAAAr7AWzUK1SbLUC1356OvcfCUKhZ2ErtPAGm0mGqU7KsIJHjyXm6ecOjgeGuhnrep_', 0),
    ('user678930212158', '6905379610512000005', 'MS4wLjABAAAA9N-SBiNZG3GoMridIzdzTgKa8hYZ9UOAON7Ei0AjqdhpWcVoJNt4dRcnUtKOpNmr', 0),
    ('user457759814425', '6905379732478002181', 'MS4wLjABAAAA5FlVtHBInfU02sSnCRA1ij55TSO_P75a0rcTCQB7eG7CY8Oaen4ypj6ZfPDzFdTn', 0),
    ('user5861052987928', '6905380906320610310', 'MS4wLjABAAAA0JE6XIMaveNwwXqjeSTL7pjBz-uBZcIuDUuyQhxw7uvIZ0BPe5qw91kWS5QpeNfM', 0),
    ('user61839525331565', '6905381478873089030', 'MS4wLjABAAAAvRdA46PLcStJuJZjjn7m5O-ey9nccQ-K2W2085iLaVcuGoJdmTQ59UCqZ5vbHW7B', 0),
    ('user6647579580780', '6905381441807811590', 'MS4wLjABAAAAUsi26lxzk_y4l4bucEOMHVNkxVL3Lf3JHxR3vHOuMrU_0A1RrKmjka3G8YIfuq5r', 0),
    ('user1707423299437', '6905381364189021189', 'MS4wLjABAAAAGrLVL2QhYxzKgeggJ7Oe5w9bBk7AShMDPPoclSuoc3-LzW1vFQyZBAcjHF00nfoE', 0),
    ('user9636621081304', '6905382082953020421', 'MS4wLjABAAAA8WY-9MDuKqcvI8irdwAD4UNA689WYpR6J7zEwQ7eBqgoUxobNc482xw-ndfaIBQP', 0),
    ('user2925615693460', '6905381420262310918', 'MS4wLjABAAAA6YEpRaJgCe5rlh34bdnQxYxVKehfZKdPX7zUI1ZXqDCPghTg6gh8cP0PvnwkhHpL', 0),
    ('user50463096750063', '6905382989477168134', 'MS4wLjABAAAAsnIixpHN6s40WVhVvQQpFAtR2n5puBD1mlZ_Si0Y9pUCzW1X3_O0jHQ2hCA4G293', 0),
    ('user3291495138943', '6905385302472262661', 'MS4wLjABAAAAj6B-lNoRZ0FnXUZ2_dwM2r1A8VNNGqk0TnoPM344ALG-x6jTORPu-cG1wcTfEsh-', 0),
    ('user5759447693443', '6905385379596256261', 'MS4wLjABAAAALxdwaIEwF4aTQlmqKWydYakoZHJglGm5MAnKW402AE9vV1NLAxeJp_nXa51htB6S', 0),
    ('user2927171388087', '6905388926594728965', 'MS4wLjABAAAA_cQumuBvsveoKUKdFeW1ee8un6yk9O_QD2YkkhNNA9FXwXnGp9tZCGMUmG2uNY3i', 0),
]

def manual_follow(stop_e):
    accs = AccountsModel().where('login_required', '=', 0).fetch_data()

    while not stop_e.is_set():
        if not len(dummy_accs):
            print('all dummy_accs exhausted')
            break
        
        username, user_id, sec_id, count = dummy_accs.pop(0)
        for idx,ac in enumerate(accs, 1):
            Log = FollowLogModel(account_id=ac.get('id'), user_id=user_id)
            if Log.is_available and Log.get('status') in ('success', 'unfollowed'):
                print('%s. %s: %s already followed' %(idx, ac.get('username'), username))
                continue

            tk = login(ac, login_flow=False)

            failed_counter = 0
            while True:
                try:
                    tk.proxy = ac.get('proxy')
                    tk.follow_by_id(user_id, sec_id)
                except (requests.exceptions.RequestException, requests.exceptions.ProxyError) as e:
                    print('%s. %s: Requests error' %(idx, ac.get('username')))

                    failed_counter += 1
                    set_new_proxy(ac)
                    tk = login(ac, login_flow=False)

                    if failed_counter >= 3:
                        break
                    continue
                except tiktok.error.CantFollowUserException as e:
                    print('%s. %s: bad user %s: %s' %(idx, ac.get('username'), username, e))
                    count = 1
                    break
                except Exception as e:
                    print('%s. %s: failed to follow %s: %s' %(idx, ac.get('username'), username, e))
                    break
                else:
                    Log.set('status', 'success').save()
                    print('%s. %s: %s followed' %(idx, ac.get('username'), username))
                    break

            if (count > 0 and idx >= count) or stop_e.is_set():
                break
    
    print('manual_follow exiting...')





def set_up_new(l, urls):
    # turn to business
    for i,username in enumerate(l):
        print('%s. %s starting..' % (i, username))
        ac=AccountModel(username=username)
        tk=login(ac, login_flow=False)

        error = 0
        biz = None
        while True:
            try:
                biz = tk.set_biz()
                break
            except (requests.exceptions.RequestException, requests.exceptions.ProxyError) as e:
                error += 1
                if error >= 2:
                    print('%s failed: %s' % (ac.get('username'), e))
                    break
                set_new_proxy(ac)
                tk.proxy = ac.get('proxy')

        # if biz:
        #     tk.set_bio(rand_bio())

        #     ac.set('data.url', urls[i]).save()
        #     resp = tk.set_url(urls[i])
        #     if not resp.user.bio_url:
        #         print('%s failed to add url: %s' % (ac.get('username'), urls[i]))
        
        

    # set bio
    # set url
    # done.

def set_url_2(ac, url):
    error_counter = 0
    print('%s setting url -> %s' %(ac.get('username'), url))

    while True:
        tk=login(ac, login_flow=False)
        try:
            biz = tk.set_biz()
            tk.set_biz_after()
            tk._send_login_flow(0)
            tk.set_url(url)
            ac.set('data.url', url).save()
            break
        except (requests.exceptions.RequestException, requests.exceptions.ProxyError) as e:
            error_counter += 1
            if error_counter >= 3:
                print('%s -> %s: requests failed: %s' % (ac.get('username'), url, e))
                break
            set_new_proxy(ac) 


if __name__ == "__main__":
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.CRITICAL)
    setup_logger('logs.log', root_logger, True)

    schedule_q = queue.Queue()
    stop_e = threading.Event()
    max_workers = 20 # max threads

    # current active account_id: (ActionClassName, time.time())
    # updated in actions_scheduler 
    running_accs = {}

    if len(sys.argv) > 1 and sys.argv[1].lower() in ['start', 'thread']:
        t1 = threading.Thread(target=actions_scheduler, args=(
            schedule_q, running_accs, stop_e))
        t1.start()

        time.sleep(1)

        t2 = threading.Thread(target=main_worker, args=(
            schedule_q, running_accs, max_workers, stop_e))
        t2.start()
        print('threads started')

    nk = [
        '🔥TIKTOK F0LLOWERS', '🔥GAIN F0LLOWERS📍', '📌GAIN F0LLOWERS📌', 
        '😍GAIN F0LLOWERS😍', '❣️❣️GAIN F0LLOWERS❣️', '💥GAIN F0LLOWERS💥', 
        '📲GAIN F0LLOWERS✔️', '📌TIKTOK F0LLOWERS', '🔥TIKTOK F0LLOWERS', 
        '📲TIKTOK F0LLOWERS', '💥TIKTOK F0LLOWERS', '😍TIKTOK F0LLOWERS', 
        '❣️TIKTOK F0LLOWERS❣️', '🎉 TIKTOK F0LLOWERS', '🎉 GAIN F0LLOWERS🎉']

    b = '#foryoupage'



# for i in range(2, 101):
#  error_counter = 0
#  ac=accs[i]
#  print('\n%s. %s setting dp' %(ac.get('username'), i))
#  while True:
#          tk=login(ac, login_flow=False)
#          try:
#                  tk.profile_image('img/dps/{}.jpg'.format(random.randint(0, 24)))
#                  break
#          except (requests.exceptions.RequestException, requests.exceptions.ProxyError) as e:
#                  error_counter += 1
#                  if error_counter >= 3:
#                          print('%s -> %s: requests failed:' % (ac.get('username'), e))
#                          break
#                  set_new_proxy(ac)