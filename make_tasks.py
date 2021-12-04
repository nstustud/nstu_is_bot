import sqlalchemy
from telegram import Bot
from r import (create_at_job)
engine = sqlalchemy.create_engine('postgresql://***REMOVED***:***REMOVED***@192.144.37.124:5432/demo')
try:
    bot = Bot("***REMOVED***")
    users_to_add = engine.execute(
        sqlalchemy.text(f"SELECT * FROM users.usergroup WHERE send_msg_time IS NOT NULL AND job_id IS NULL")
        )
    for row in users_to_add:
        try:
            job_id = create_at_job(row['user_id'], row['send_msg_time'].strftime('%H:%M'))
            with engine.connect() as conn:
                result = conn.execute(
                    sqlalchemy.text(f"UPDATE users.usergroup SET job_id = :jid WHERE user_id = :uid"), 
                    uid = row['user_id'],
                    jid = job_id
                    )
        except:
            pass                
except Exception as e:
    print(e)
    pass