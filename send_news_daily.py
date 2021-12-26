import sys
import sqlalchemy
import locale 
from telegram import Bot
from misc.config import bot_token, db_connection_string, SQL_NOW

engine = sqlalchemy.create_engine(db_connection_string)

locale.setlocale(locale.LC_ALL, 'ru_RU.UTF-8')


def get_news_from_db():
    news_text = ''
    with engine.begin() as conn:
        news_query = conn.execute(sqlalchemy.text(f'SELECT title, url, shorttext, news_date FROM test.news WHERE news_date > ({SQL_NOW} - INTERVAL \'1 DAY\')'))
        for row in news_query:
            news_text += row['title'] + '\n' + (('[' + (row['shorttext']) + ']\n') if row['shorttext'] is not None else '') + row['url'] + '\n' + row['news_date'].strftime('%c') + '\n\n'
    return news_text


try:
    user_id = int(sys.argv[1])
    bot = Bot(bot_token)
    news_text = get_news_from_db()
    if news_text is not None or news_text == '':
        bot.send_message(user_id, news_text, parse_mode='HTML', disable_web_page_preview=True)   # we can pass user_id as chat_id for private messages
except Exception as e:
    print(e)
    pass
try:
    with engine.connect() as conn:
        result = conn.execute(sqlalchemy.text("UPDATE users.usergroup SET news_job_id = NULL WHERE user_id = :uid"), uid=user_id)
except Exception as e:
    print(e)
