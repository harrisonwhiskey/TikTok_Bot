class UserInfo:
    SIMPLE_FIELDS = (
        'gender', 'birthday', 'nickname', 'watch_status', 'follower_count', 'country', 'following_count',
        'location', 'account_region', 'region', 'current_region', 'total_favorited', 'favoriting_count',
        'show_favorite_list', 'is_email_verified', 'has_email', 'email', 'is_phone_binded', 'bio_url'
    )

    def __init__(self, data):
        self.user_id = data.get('uid')
        self.username = data.get('unique_id')
        self.sec_id = data.get('sec_uid')
        try:
            self.avatar_url = data.get('avatar_larger')['url_list'][0]   
        except Exception:
            self.avatar_url = ''
        self.is_followed_by = data.get('follower_status') != 0
        self.is_following = data.get('follow_status') != 0
        self.video_count = data.get('aweme_count')
        self.bio = data.get('signature')
        self.langauge = data.get('signature_language', '')
        self.is_verified = data.get('custom_verify') not in ('', None)
        self.is_private = data.get('secret') == 1
        self.instagram_id = data.get('ins_id')
        try:
            self.is_url_enabled = data.get('bio_permission').get('enable_url')
        except AttributeError:
            self.is_url_enabled = False
        try:
            self.share_url = data.get('share_info').get('share_url')
        except AttributeError:
            self.share_url = ''
        self.is_banned = False

        if not self.username and not self.sec_id:
            self.is_banned = True
            

        for field in UserInfo.SIMPLE_FIELDS:
            setattr(self, field, data.get(field))


class ConversationInfo:
    def __init__(self, conversation=None):
        if conversation:
            self.id = conversation['conversation_id']
            self.short_id = conversation['conversation_short_id']
            self.type = conversation['conversation_type']
            self.ticket = conversation['ticket']
            self.participants = [p.get(
                'user_id') for p in conversation['first_page_participants']['participants']]
            self.owner = conversation['owner']


class CommentInfo:
    """
    status -> 2: video comment, 7: comment reply
    """
    def __init__(self, data):
        self.id = data['cid']
        self.text = data['text']
        self.video_id = data['aweme_id']
        self.create_time = data['create_time']
        self.digg_count = data['digg_count']
        self.replies_count = data.get('reply_comment_total')
        self.status = data['status']
        try:
            self.user = UserInfo(data['user'])
        except KeyError:
            pass


class VideoInfo:
    def __init__(self, data):
        self.id = data['aweme_id']
        self.caption = data['desc']
        self.create_time = data['create_time']
        self.music_info = {}
        try:
            self.music_info = {
                'id': data.get('music').get('id'),
                'title': data.get('music').get('title'),
                'author': data.get('music').get('author'),
                'owner_id': data.get('music').get('owner_id'),
                'owner_handle': data.get('music').get('owner_handle'),
                'sec_uid': data.get('music').get('sec_uid'),
                'url': data.get('music').get('play_url').get('uri'),
            }
        except Exception:
            # no added music
            pass
        try:
            self.url = data['video']['play_addr']['url_list'][0]
        except IndexError:
            self.url = None
        self.share_url = data['share_url']
        self.comment_count = data['statistics']['comment_count']
        self.play_count = data['statistics']['play_count']
        self.like_count = data['statistics']['digg_count']
        self.share_count = data['statistics']['share_count']
        self.region = data['region']
        self.duration = data['duration']
        self.author = UserInfo(data['author'])
        try:
            self.url_with_logo = data['video']['download_addr']['url_list'][0]
        except Exception:
            self.url_with_logo = ''
        self.is_available = not data['status']['is_prohibited']
        self.allow_comment = data['status']['allow_comment']
        