import logging
import time
import random, string
from datetime import datetime
import requests
from requests.exceptions import RequestException, ProxyError

from tiktok.tiktok import TikTok
from tiktok.utils import generate_random, username_to_id
import tiktok.error

# from models import ProxyModel

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

LOG_DIR = 'logs\\'
DB_DIR = 'db\\'

def setup_logger(file_name, logger, propagate=False):
    formatter = logging.Formatter(
        '%(asctime)s - (%(name)s %(threadName)s)  - %(levelname)s - %(message)s', datefmt='%m/%d/%Y %I:%M:%S%p'
    )
    handler = logging.FileHandler(f'{LOG_DIR}{file_name}', encoding='utf-8')
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = propagate


setup_logger('app.log', logger)

def random_str(size=8):
    chars = string.ascii_uppercase + string.ascii_lowercase + string.digits
    return ''.join(random.choice(chars) for x in range(size))

def proxy_error(p):
    from models import ProxyModel
    if not p:
        return

    p = p.split(',')[0]
    p = p.split(':')
    proxy = p[0]
    port = p[1]
    p = ProxyModel(proxy=proxy, port=port)
    if not p.is_available:
        print('proxy not available')
    else:
        p.set('data.error', p.get('data.error') + 1).save()

def set_new_proxy(ac, country=None):
    error_counter = 0
    while True:
        if country:
            proxy = f'hp_whisk1843jmztw4181:3N8uOuBgXtowwYyN_country-{random.choice(PROXY_COUNTRIES)}_session-{random_str()}@isp2.hydraproxy.com:9989'
        else:
            proxy = f'hp_whisk1843jmztw4181:3N8uOuBgXtowwYyN_session-{random_str()}@isp2.hydraproxy.com:9989'

        proxies = {'http': f'http://{proxy}', 'https': f'http://{proxy}'}
        proxy_ip = None
        for _ in range(3):
            try:
                proxy_ip = requests.get('https://api.ipify.org', proxies=proxies).text
                break
            except Exception as e:
                time.sleep(1)
        
        if not proxy_ip:
            # print('%s: getting proxy ip error (%s) -> %s' %(ac.get('username'), error_counter, proxy))
            error_counter += 1
            if error_counter >= 4:
                ac.set('proxy', proxy).save()
                return
            continue

        ac.set('proxy', proxy).save()
        return


def login(Account, folder=None, force_login=False, login_flow=True, force_login_flow=False, no_proxy=False, proxy=False):
    '''
    :Account: -> AccountModel
    '''
    if not Account.is_available:
        raise Exception('Account is not available')
    
    if Account.get('login_required') == 1 and not force_login:
        raise Exception('Re-login required for %s' %Account.get('username'))
    

    Tik = TikTok() if not folder else TikTok(folder)
    if not Tik.settings.has_user(Account.get('username')):
        raise Exception('Account do not exist')

    if not login_flow:
        Tik.login_flow = False
    else:
        if force_login_flow:
            pass
        else:
            last_login_ts = Account.get('last_login')
            if last_login_ts and last_login_ts.timestamp() + (3600 * 12) > time.time():
                Tik.login_flow = False
            else:
                Account.set('last_login', datetime.now())
            # Tik.login_flow = False
    
    if not proxy:
        proxy = '' if no_proxy else Account.get('proxy')

    failed_counter = 0
    while True:
        try:
            Tik.login(Account.get('username'), Account.get('password'), proxy=proxy, force_login=force_login)
            if Tik.login_flow == True:
                Account.set('login_required', 0)
            break
        except tiktok.error.BadRequestException:
            logger.exception('%s. %s: Failed to login.' %(Account.get('id'), Account.get('username')))
            Account.set('login_required', 1).save()
            raise
        except tiktok.error.AccountDisabledException:
            logger.exception('%s. %s: Account disabled' %(Account.get('id'), Account.get('username')))
            Account.set('login_required', 2).save()
            raise
        except tiktok.error.LoginExpiredException as e:
            logger.error('%s. %s: Login Expired: %s' %(Account.get('id'), Account.get('username'), e))
            Account.set('login_required', 1).save()
            raise
        except tiktok.error.CaptchaErrorException as e:
            logger.debug('%s: captcha required %s' %(Account.get('username'), e))
            raise
        except (RequestException, ProxyError, tiktok.error.TikTokException) as e:
            break
            logger.error('%s. %s Failed to login. %s Requests error: %s' %(
                Account.get('id'), Account.get('username'), Account.get('proxy'), e))

            failed_counter += 1
            if '502' in str(e):
                set_new_proxy(Account)
                proxy = Account.get('proxy')

            if failed_counter >= 3:
                set_new_proxy(Account)
                raise

        except Exception:
            logger.exception('%s. %s: Failed to login.' %(Account.get('id'), Account.get('username')))
            raise

    Account.set('last_login', datetime.now()).save()
    return Tik

def time_int(arg):
    ''' returns int representation of HH:MM time to HHMM
    :arg: datetime.datetime -> will extract the hours and minutes and return HHMM
        : string -> eg: '18:30' | '1830' -> 1830. '00:00' -> 0. '00:30' -> 30. '06:20' -> 620  
    '''
    if type(arg) is datetime:
        minute = str(arg.minute)
        if len(minute) == 1:
            minute = '0' + minute
        return int('{}{}'.format(arg.hour, minute))
    elif type(arg) is str:
        if ':' in arg:
            arg = arg.split(':')
            return int('{}{}'.format(arg[0], arg[1]))
        else:
            return int(arg)
    else:
        raise TypeError('Invalid argument')


comments = [
    'hey nice', 'awesome', 'hehe', 'haha', 'i ding that',
    'im comin', 'lol nice', 'nice', 'oh dang', 'hell ya',
    'wow lol', 'wow', 'that\'s the best', 'lol', 'lmao', 'i love it', 
    'i\'m a fan', 'im a fan', 'im your fan', 'fyp', 'ooohhh', 
    'wow this required so much talent', 'too much', 'TikTok', 'sweet',
    'aaaaaah', 'NO LOVE', 'beautiful', 'this is gorgeous', 
    'this looks lovely', 'OMG', "omg hahahaha😂😂😂", 
    "so funny and awesome❤️😍", "Omg amazing", "Hi", 
    "WHAT???😂😂", "not first😁", "hey be nice !!😀👍🎶",
    "how re u feeling 😳😅", "BEST  ON TIKTOK", "ok u for the win😌❤️", "Do one with just 😌 I wanna see sum 😂", "YAS ", "just got yeeted 😂", "really said 🦟🦗🦟🦗🦟🦗🦟🦗🦟🦗🦟🦗🦟🦟🦗🦟🦗😳 👛", "Your dances very well🥵🥵💥💥🔥🔥👁️👄👁️", "done yeeted him", "said 👁👄👁 🦗🦟🦗🦟🦗🦟🦗", "POPPED OFF WITH HER SpLITS😂😂😂😂😂", "Οmg  killed that literally 😂❤️", " said “move”😏🕺🏾", "YAAAAASS 😃😃🤠🤠🤩", "looks like this 😱", "Dam bro these comments are ✨fresh✨", "that split tho", "love this yyy ❤️😍", "wins", "anyone else born on their birthday??", "WHY YOU PUSHED YOUR LIKE THAT 😭😭", "IT WAS THE SHOVE FOR ME", "said move", " wins", "told me put a heart in a bag🥺", "need to chill😳", "OMG NO NO", "nothing goes un this video😅😅😅😅😌", "anyone else born on their birthday??", "hey we look the same", "Dose the king reply me😳😳😳", "said😱😱￼￼", "Your carried the video", " made me laugh so much!!!", "Can’t believe  got pushed away🤯🥺", "Is your ok?😂", "like 👁💧👄💧👁 I wanted to dance 💃", "perfect", "perfect", "THO 😂😂He always steals the show", "Who else saw pushed his from the bottom😳😂", "Charli damelio’s leaked video 😳😳", "There's too much in it", "Omg this is lit ♥️♥️🥺", "love this FAM very much", "Michael made me laugh to the top", "1m ago gang —————&gt;", "Omggggggggggggggg please notice meeeeeee plzzz", "how am I this early and it still has so many likes!!", "y'all went off😂", "People who don’t like peaches🔜", "okay but the girl at the end popped offffff 😳😳😳", "Does he reply tho?? Plz do", "Your sis killed it 🔥", "Omg amazing", "Hi", "😳😳😳 the split", "I’m deadddd 😭😂😂😂", "First", "his reply game 📉😭🎰📈😁❤️", "hi", "s entry is 🔥 😂😂", "Won't breathe until he replies", "who come to read comments 😁😁", "Ur fam be funny tho Lmaoo", "said 🦟🐜🦗🐜🦗🦟🐜🦟🦗🐜🦟🦗🐜🦟🦗", "Ahhahaha !!!", "NICE DANCE HAHA😂", "Omg 73", "Hi", "How he pushed the 😂", "HI PLIS REPLY I WILL CRY CAN YOU SAY HI NANA", "Johnathon’s face at the end 💀", "I really thought Michael was about to pop off 😔", " said Gilbert", "Ur brother really said:🦟🦗🦟🦗💀", "did you guys made up this ? if you do 😂😂😂😂😂😂😂", "Does he reply to his fans?🥺 killed it btwww🔥", "watching at 11pm like😐", "25m late I’m a big fan :3", " does the splits everyone 😲", "IM CRYINGGGGG 🤣🤣🤣🤣", "I'm not first or last I'm here", "Imao", "omg hahahaha😂😂😂", "Pop awf", "this has to be my fave video of all 💀💀😂", "WHAT???😂😂", "not first😁", "hey be nice !!😀👍🎶", "Omg nooo- he pushed mama😂😂", "omg", "your little bro hit hard doe😳", "Your my favorite tiktoker I swear 🤟🏼🤟🏼", "╱╰━━━╯╱╱╱╱╱╱╱╱", "Omg pop off girl 😌", "woke up chris breezily", "I LOVE YOUR ❤", "ROAD TO 10K WHIT ONE VIDEO🐐👑", "Beatiful ❤😊", "Dose the king reply me😳😳😳", "said:🦟🦗🦟🦗🦟🦗🦟🦗🦟🦗🦟🦗🦟", "Hi", "Does the king replay me?", "what", "This  🥰👌", "be like:Out of my waya", "You guys are so funny and awesome❤️😍", "🥺 Does the king reply", "lil tay💸🤑🔫is typing...", "That kick tho 😏", "Do u replay", "Love this  😂😂", "Hahahaha", "lol", "Early", "I love it 🥰🤣🤣🤣🤣🤣", "maiko I'm ur biggest fan of all 🥺", "lol", "nice🥰🥰🥰", "your funny😂😂😂😂", "sis snapped", "Is your ok looks hurt", "Lmaooo", " passed the vibe check 🥺", "That split was so straight", "Can I be a part of this ? 🥺", "Where are his fans at?", "hahaha hahaha hahaha my god I can't dstop😂😂😂😂😂", "it's funny when pushed the😂😂😂", "negative thinkers joined:", "He said 😁😅😱", "omg😅😅😅😂😂😂😂😂 SIS DID IT BETTER😅😅😏", "Ok I love this video 😳🤩", "ur whole  is amazing-", "This really be a dance ", "Little man got it tho 😳", "I love this lol🥺", " GET IT GIRL 🤩🤩🤣🤣🙌🙌🙌", "Sis snapped", "Yass", "Your really said PERIODT with that split 😂😭", "nice  🥰", " won no cap👁️👄👁️", "that boi that boi sus", "I like the", "killed it", "The comments are ✨outta da oven fresh ✨", "HOW COULD YOU 😭😭", "lmao imagine being an involved 🤪", "Okay so who came straight to the comments", "i loved", "whEN HE PUSHED HIS LMFAOOOO", "yeet", "Lil at the end for the win!!!!", "this  is getting dangerouss", "We want to see your dance with y’all", "I went 😯😧😲😳",
]


emojis = [
    '😀','😁','😂','🤣','😃','😄','😅','😆','😉','','😊','😋','😎','😍','😘','🥰','😗','😙','😚','🙂','','🤗','🤩','🤔','🤨','',
    '😶','🙄','😏','😮','🤐','😯','😪','😫','😴','','😌','😛','😜','😝','🤤','😒','😓','😔','😕','🙃','','🤑','😲','☹️','🙁','',
    '😞','😟','😤','😦','😧','😨','😩','🤯','😬','','😰','😱','🥵','🥶','😳','🤪','😵','😠','🤬','😷','','🤒','🤕','🤢','🤮','',
    '🤧','😇','🤠','🤡','🥳','🥴','🥺','🤥','🤫','','🤭','🧐','🤓','🤖','💩','😺','😸','😹','😻','😼','','😽','🙀','😿','😾','',
    '🤲','👐','🙌','👏','🤝','👍','👎','👊','✊','','🤛','🤜','🤞','✌️','🤟','🤘','👌','👈','👉','👆','','👇','☝️','✋','🤚','🖐','🖖','👋','',
    '🤙','🙏','👂','👣','😐','😑','😖',''
]

def generate_comment():
    return f'{random.choice(comments)} {random.choice(emojis)}'


def device_manager(Account, tk=None, new_account=False, folder=None, db='devices.db'):
    from models import DeviceModel, DevicesModel
    return False

    if not tk:
        tk = TikTok(folder)
        if new_account:
            tk.settings.set_user(Account.get('username'))
        else:
            tk.login_flow = False
            tk.login(Account.get('username'), Account.get('password'))

    new_device = (
        DevicesModel(db)
        .where('used_count', '=', 0)
        .order_by('last_action_date', 'ASC')
        .limit(1)
        .fetch_data()
    )
    if not new_device:
        return False
        
    new_device = new_device[0]

    if not new_account:
        # insert or update old device
        old_device = DeviceModel(db=db, device_id=tk.settings.get('device_id'))
        if old_device.is_available:
            old_device.set('used_count', 0)
            old_device.set('tags', '')
            old_device.set('last_action_date', datetime.now())
        else:
            (
                old_device.set('device_string', tk.settings.get('device_string'))
                .set('google_aid', tk.settings.get('google_aid'))
                .set('openudid', tk.settings.get('openudid'))
                .set('uuid', tk.settings.get('uuid'))
                .set('device_id', tk.settings.get('device_id'))
                .set('install_id', tk.settings.get('install_id'))
            )
        old_device.save()

    tk.settings.set('device_string', new_device.get('device_string'))
    tk.settings.set('google_aid', new_device.get('google_aid'))
    tk.settings.set('openudid', new_device.get('openudid'))
    tk.settings.set('uuid', new_device.get('uuid'))
    tk.settings.set('device_id', new_device.get('device_id'))
    tk.settings.set('install_id', new_device.get('install_id'))
    tk.settings.set_cookie('install_id', new_device.get('install_id'))

    (
        new_device.set('used_count', 1)
        .set('last_action_date', datetime.now())
        .set('tags', Account.get('id'))
        .save()
    )
    return True


PROXY_COUNTRIES = [
    # 'Russia',
    'UnitedStates',
    'Canada','Afghanistan','Albania','Algeria','Argentina','Armenia','Aruba','Australia','Austria','Azerbaijan','Bahamas','Bahrain','Bangladesh','Belarus','Belgium','BosniaandHerzegovina','Brazil','BritishVirginIslands','Brunei','Bulgaria','Cambodia','Cameroon','Chile','China','Colombia','CostaRica','Croatia','Cuba','Cyprus','Czechia','Denmark','DominicanRepublic','Ecuador','Egypt','ElSalvador','Estonia','Ethiopia','Finland','Georgia','Germany','Ghana','Greece','Guatemala','HashemiteKingdomofJordan','HongKong','Hungary','India','Indonesia','Iran','Iraq','Ireland','Israel','Italy','Jamaica','Japan','Kazakhstan','Kenya','Kosovo','Kuwait','Latvia','Liechtenstein','Luxembourg','Macedonia','Madagascar','Malaysia','Mauritius','Mexico','Mongolia','Morocco','Myanmar','Nepal','Netherlands','NewZealand','Nigeria','Norway','Oman','Pakistan','Palestine','Panama','PapuaNewGuinea','Paraguay','Peru','Philippines','Poland','PuertoRico','RepublicofLithuania','Romania','SaudiArabia','Senegal','Serbia','Seychelles','Singapore','Slovakia','Slovenia','Somalia','SouthAfrica','SouthKorea','Spain','SriLanka','Sudan','Suriname','Sweden','Switzerland','Syria','Taiwan','Thailand','TrinidadandTobago','Tunisia','Turkey','Uganda','Ukraine','UnitedArabEmirates','UnitedKingdom','Venezuela','Vietnam','Zambia'
]


'''
Test classes
'''
class Users:
    def __init__(self):
        self.username = generate_random()
        self.user_id = generate_random()
        self.sec_id = generate_random()

class Videos:
    def __init__(self):
        self.id = generate_random()
        self.url = 'https://tiktok.com/vid/{}'.format(generate_random())
        self.url_with_logo = 'https://tiktok.com/vid/{}'.format(generate_random())

class Response:
    def __init__(self):
        self.staus = 'ok'
        self.user = Users()
        self.videos = [Videos() for i in range(20)]

class Fuf:
    def __init__(self):
        self.status = 'ok'
        self.max_time = 10
        self.offset = 30
        self.has_more = True
        self.users = [Users() for i in range(20)]

class T:
    def __init__(self):
        pass
    def get_user_info(self, sec_id, username=None):
        return Response()

    def get_followers(self, arg1, arg2, arg3, arg4):
        return Fuf()

    def get_followings(self, arg1, arg2, arg3, arg4):
        return Fuf()
    
    def follow_by_id(self, user_id, user_sec_id):
        return Response()
    
    def get_user_videos(self, user_sec_id):
        return Response()
    
    def like_video_by_id(self, video_id):
        return Response()

def _login(Account):
    return T()


if __name__ == "__main__":
    pass