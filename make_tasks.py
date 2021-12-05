import sqlalchemy
from telegram import Bot
from r import (create_at_job, get_offset_date)
import misc.config as config
from datetime import datetime

engine = sqlalchemy.create_engine(config.db_connection_string)
try:
    bot = Bot(config.bot_token)
    users_to_add = engine.execute(
        sqlalchemy.text("SELECT * FROM users.usergroup WHERE send_msg_time IS NOT NULL AND job_id IS NULL")
    )
    for row in users_to_add:
        try:
            job_id = create_at_job(row['user_id'], row['send_msg_time'].strftime('%H:%M'))
            with engine.connect() as conn:
                result = conn.execute(
                    sqlalchemy.text("UPDATE users.usergroup SET job_id = :jid WHERE user_id = :uid"),
                    uid=row['user_id'],
                    jid=job_id
                )
        except Exception:
            pass

    users_to_add = engine.execute(
        sqlalchemy.text("SELECT * FROM users.usergroup WHERE offset_time IS NOT NULL AND job_id IS NULL")
    )
    for row in users_to_add:
        try:
            date_string = get_offset_date(
                user_id=row['user_id'],
                input_time=datetime.combine(datetime.min, row['offset_time'])
            )
            job_id = create_at_job(row['user_id'], date_string)
            with engine.connect() as conn:
                result = conn.execute(
                    sqlalchemy.text("UPDATE users.usergroup SET job_id = :jid WHERE user_id = :uid"),
                    uid=row['user_id'],
                    jid=job_id
                )
        except Exception as e:
            print(e)
            pass

except Exception as e:
    print(e)
    pass
