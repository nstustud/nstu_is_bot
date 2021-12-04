import datetime
import sqlalchemy
import sys
from telegram import Bot
from r import (get_current_week, get_user_day_timetable, USER_FREE_DAY)
engine = sqlalchemy.create_engine('postgresql://***REMOVED***:***REMOVED***@192.144.37.124:5432/demo')
try:
user_id = int(sys.argv[1])
    bot = Bot("***REMOVED***")
    user_timetable=get_user_day_timetable(user_id)
    bot.send_message(user_id, user_timetable if user_timetable != None else USER_FREE_DAY) #we can pass user_id as chat_id for private messages
except Exception as e:
    print(e)
    pass
try:
    with engine.connect() as conn:
        result = conn.execute(sqlalchemy.text(f"UPDATE users.usergroup SET job_id = NULL WHERE user_id = :uid"), uid = user_id)
except Exception as e:
    print(e)