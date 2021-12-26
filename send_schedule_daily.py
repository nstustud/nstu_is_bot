import sys
import sqlalchemy
from telegram import Bot
from misc.config import bot_token, db_connection_string
from r import get_user_day_timetable

engine = sqlalchemy.create_engine(db_connection_string)
try:
    user_id = int(sys.argv[1])
    bot = Bot(bot_token)
    user_timetable = get_user_day_timetable(user_id)
    if user_timetable is not None or user_timetable == '':
        bot.send_message(user_id, user_timetable)   # we can pass user_id as chat_id for private messages
except Exception as e:
    print(e)
    pass
try:
    with engine.connect() as conn:
        result = conn.execute(sqlalchemy.text("UPDATE users.usergroup SET job_id = NULL WHERE user_id = :uid"), uid=user_id)
except Exception as e:
    print(e)
