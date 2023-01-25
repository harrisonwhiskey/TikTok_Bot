-- accounts table. contains tiktok accounts added to the bot
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY NOT NULL,
    username TEXT,
    user_id INTEGER,
    user_sec_id TEXT,
    follower_count INTEGER,
    following_count INTEGER,
    video_count INTEGER,
    bio TEXT,
    language TEXT,
    is_private INTEGER,
    added_date TIMESTAMP,
    is_fetched INTEGER,
    comment_fetched INTEGER,
    data JSON
);

-- accounts table. contains tiktok accounts added to the bot
CREATE TABLE IF NOT EXISTS source (
    id INTEGER PRIMARY KEY NOT NULL,
    username TEXT,
    user_id INTEGER,
    user_sec_id TEXT,
    follower_count INTEGER,
    following_count INTEGER,
    status INTEGER,
    last_activity TIMESTAMP,
    added_date TIMESTAMP,
    data JSON
);

CREATE TABLE IF NOT EXISTS daily_source (
    id INTEGER PRIMARY KEY NOT NULL,
    username TEXT,
    user_id INTEGER,
    user_sec_id TEXT,
    follower_count INTEGER,
    following_count INTEGER,
    follower_counter INTEGER,
    is_active INTEGER,
    last_activity TIMESTAMP,
    added_date TIMESTAMP,
    data JSON
);