from models import Database

with Database() as db:
	db.create_tables('db/tiktokbot_schema.sql')

with Database('tiktok_users.db') as db:
	db.create_tables('db/tiktok_users_schema.sql')


print('done.')