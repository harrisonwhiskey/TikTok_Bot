-- schema for tiktok bot.

-- accounts table. contains tiktok accounts added to the bot
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY NOT NULL,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    user_id INTEGER,
    user_sec_id TEXT,
    proxy TEXT,
    active_start INTEGER,
    active_end INTEGER,
    last_login TIMESTAMP,
    last_action_date TIMESTAMP,
    added_date TIMESTAMP NOT NULL,
    tags TEXT,
    data JSON,
    login_required INTEGER
);


-- auto_follow settings
CREATE TABLE IF NOT EXISTS follow_schedule (
    id INTEGER PRIMARY KEY NOT NULL,
    account_id INTEGER NOT NULL,
    target JSON,
    filters JSON,
    settings JSON,
    is_active INTEGER,
    tags TEXT,
    active_start INTEGER,
    active_end INTEGER,
    schedule_date TIMESTAMP,
    last_action_date TIMESTAMP,
    data JSON,
    FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
);
-- auto_follow logs
CREATE TABLE IF NOT EXISTS follow_log (
    id INTEGER PRIMARY KEY NOT NULL,
    account_id INTEGER NOT NULL,
    status TEXT,
    user_id INTEGER,
    user_sec_id TEXT,
    data JSON,
    followed_date TIMESTAMP,
    FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
);


-- auto_video_like settings
CREATE TABLE IF NOT EXISTS video_like_schedule (
    id INTEGER PRIMARY KEY NOT NULL,
    account_id INTEGER NOT NULL,
    target JSON,
    filters JSON,
    settings JSON,
    is_active INTEGER,
    tags TEXT,
    active_start INTEGER,
    active_end INTEGER,
    schedule_date TIMESTAMP,
    last_action_date TIMESTAMP,
    data JSON,
    FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
);
-- auto_video_like logs
CREATE TABLE IF NOT EXISTS video_like_log (
    id INTEGER PRIMARY KEY NOT NULL,
    account_id INTEGER NOT NULL,
    status TEXT,
    user_id INTEGER,
    user_sec_id TEXT,
    video_id INTEGER,
    data JSON,
    liked_date TIMESTAMP,
    FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
);


-- auto_comment settings
CREATE TABLE IF NOT EXISTS comment_schedule (
    id INTEGER PRIMARY KEY NOT NULL,
    account_id INTEGER NOT NULL,
    target JSON,
    filters JSON,
    settings JSON,
    is_active INTEGER,
    tags TEXT,
    active_start INTEGER,
    active_end INTEGER,
    schedule_date TIMESTAMP,
    last_action_date TIMESTAMP,
    data JSON,
    FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
);
-- auto_comment logs
CREATE TABLE IF NOT EXISTS comment_log (
    id INTEGER PRIMARY KEY NOT NULL,
    account_id INTEGER NOT NULL,
    status TEXT,
    user_id INTEGER,
    user_sec_id TEXT,
    video_id INTEGER,
    comment_id INTEGER,
    comment TEXT,
    data JSON,
    commented_date TIMESTAMP,
    FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
);


-- auto_unfollow settings
CREATE TABLE IF NOT EXISTS unfollow_schedule (
    id INTEGER PRIMARY KEY NOT NULL,
    account_id INTEGER NOT NULL,
    target JSON,
    filters JSON,
    settings JSON,
    is_active INTEGER,
    tags TEXT,
    active_start INTEGER,
    active_end INTEGER,
    schedule_date TIMESTAMP,
    last_action_date TIMESTAMP,
    data JSON,
    FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
);
-- auto_unfollow logs
CREATE TABLE IF NOT EXISTS unfollow_log (
    id INTEGER PRIMARY KEY NOT NULL,
    account_id INTEGER NOT NULL,
    status TEXT,
    user_id INTEGER,
    user_sec_id TEXT,
    data JSON,
    unfollowed_date TIMESTAMP,
    FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

-- proxies
CREATE TABLE IF NOT EXISTS proxies (
    id INTEGER PRIMARY KEY NOT NULL,
    proxy TEXT,
    port TEXT,
    username TEXT,
    password TEXT,
    used_count INTEGER,
    rotate INTEGER,
    last_action_date TIMESTAMP,
    added_date TIMESTAMP NOT NULL,
    tags TEXT,
    data JSON
);