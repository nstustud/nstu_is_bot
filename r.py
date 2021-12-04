import datetime
import logging
import tempfile
from subprocess import call

import pandas
import sqlalchemy
import telegram
from rapidfuzz import fuzz, process
from telegram import (ForceReply, InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyKeyboardMarkup, ReplyKeyboardRemove)
from telegram.ext import (CallbackQueryHandler, CommandHandler,
                          ConversationHandler, Filters, MessageHandler,
                          Updater)
from transliterate import get_available_language_codes, translit

# Enable logging

menu_keyboard_markup = ReplyKeyboardMarkup([['Расписание', 'Новости'],['Настройки бота'],['Сменить группу']],
                                                one_time_keyboard=False,
                                                resize_keyboard=True
                                                )


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

timetable_name = "test.tt_new"

USER_FREE_DAY="Сегодня не учишься, угомонись"

days_dict = {1:'Пн', 2:'Вт',3:'Ср',4:'Чт',5:'Пт',6:'Сб',7:'Вс'}

CANCEL_INPUT = -1
ONE, TWO, THREE = range(3)
engine = sqlalchemy.create_engine('postgresql://***REMOVED***:***REMOVED***@192.144.37.124:5432/demo')


def start(update, context):
    update.message.reply_text(
        'Привет. Я бот-помощник студента НГТУ \n'
        'Отправьте /cancel если хотите прервать общение.\n\n'
        'Введите вашу группу', reply_markup=ForceReply())
    return ONE

def timetable_markup(chosen_time):
    keyboard = [[InlineKeyboardButton(f"Расписание на текущий день {'✅' if chosen_time == 0 else ''}", callback_data=0)],
            [InlineKeyboardButton(f"Расписание на оставшуюся неделю {'✅' if chosen_time == 1 else ''}", callback_data=1)]]
    return InlineKeyboardMarkup(keyboard)

def settings_markup(chosen_parameter):
    keyboard = [[InlineKeyboardButton(f"Отменить ежедневную отправку{'✅' if chosen_parameter == 0 else ''}", callback_data=0)],
                [InlineKeyboardButton(f"Выбрать время отправки расписания{'✅' if chosen_parameter == 1 else ''}", callback_data=1)],
                [InlineKeyboardButton(f"Выбрать смещение времени перед парами {'✅' if chosen_parameter == 2 else ''}", callback_data=2)],
                [InlineKeyboardButton("Назад", callback_data=CANCEL_INPUT)]]
    return InlineKeyboardMarkup(keyboard)                                       

def get_true_groups_name(input, group_names):
    score =  process.extract(translit(input.upper(),'ru'), group_names, scorer=fuzz.partial_ratio, limit=5)
    return list(map(list,zip(*score)))[0]

def gender(update, context):
    try:
        with engine.begin() as conn:
            group_names_query = conn.execute(sqlalchemy.text("SELECT name FROM test.group_names"))
            group_names = [row['name'] for row in group_names_query]

            true_group = get_true_groups_name(update.message.text, group_names)
            keyboard = []
            for group in true_group:
                keyboard.append([InlineKeyboardButton(group, callback_data = group)])
            keyboard.append([InlineKeyboardButton('Другая группа', callback_data = 'Другая группа')])
            update.message.reply_text('Выберите группу', reply_markup = InlineKeyboardMarkup(keyboard))
            return TWO

    except Exception as e: #Ignored, becasue of INSERT ON CONFLICT
        logger.info(str(e))


def select_group(update, context):
    query = update.callback_query
    if query.data == 'Другая группа':
        query.bot.delete_message(query.message.chat_id, query.message.message_id)
        change_user_group(query,context)
        return ONE
    try:
        query.answer()
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("INSERT INTO users.usergroup (user_id, group_name) VALUES (:u_id, :gn) ON CONFLICT (user_id) DO UPDATE SET group_name = :gn"), u_id=query.from_user.id, gn=query.data)
            query.bot.send_message(query.message.chat_id, f'Ваша группа {update.callback_query.data}!\nПоздравляю вас\n', reply_markup=menu_keyboard_markup)
            query.bot.delete_message(query.message.chat_id, query.message.message_id)
            
    except sqlalchemy.exc.IntegrityError: #Ignored, becasue of INSERT ON CONFLICT
        query.bot.send_message(query.message.chat_id, f'Вы уже есть тут, шо вам еще надо?', reply_markup=menu_keyboard_markup)
        query.bot.delete_message(query.message.chat_id, query.message.message_id)
    return ConversationHandler.END

def change_user_group(update, context):
    update.message.reply_text('Введите имя группы:', reply_markup=ForceReply())
    return ONE


def cancel(update, context):
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.first_name)
    update.message.reply_text('Bye! I hope we can talk again some day.',
                              reply_markup=ReplyKeyboardRemove())

    return ConversationHandler.END

def get_user_day_timetable(user_id):
    user_timetable=""
    with engine.connect() as conn:
        result = conn.execute(sqlalchemy.text(f"SELECT * FROM {timetable_name} WHERE group_name IN (SELECT group_name FROM users.usergroup WHERE user_id = :uid LIMIT 1) AND day = (select extract(isodow from now())) AND week{get_current_week()} = true ORDER BY starttime"), uid = user_id)
        if result.rowcount == 0:
            return None
        else:
            for row in result:
                user_timetable+=f"\n{row['starttime']}-{row['endtime']} {'['+row['tsw_name']+'] ' if row['tsw_name'] != None else ''} {row['classname']} {row['rooms']} {row['teacher1']} {row['teacher2']}"
            return user_timetable

def get_user_week_timetable(user_id):
    with engine.connect() as conn:
        result = pandas.read_sql(sqlalchemy.text(f"SELECT * FROM {timetable_name} WHERE group_name IN (SELECT group_name FROM users.usergroup WHERE user_id = :uid LIMIT 1) AND week{get_current_week()} = true AND ((day = EXTRACT(isodow from now()) AND endtime > to_char(CURRENT_TIMESTAMP AT TIME ZONE \'Asia/Novosibirsk\', \'HH24:MI\')) OR (day>EXTRACT(isodow from now()))) ORDER BY day, starttime"), conn, params={'uid':user_id})
    days_timetable_list = []
    days = result[['day']].groupby('day').count()
    for day_idx in days.index:
        current_day_text = ""
        current_day_timetable = result[result['day']==day_idx]
        current_day_text+=days_dict[day_idx]+'\n'
        for _index, row in current_day_timetable.iterrows():
            current_day_text+=f"{row['starttime']}-{row['endtime']} {'['+row['tsw_name']+'] ' if row['tsw_name'] != None else ''} {row['classname']} {row['rooms']} {row['teacher1']} {row['teacher2']}\n"
        days_timetable_list.append(current_day_text)
    return days_timetable_list


def proceed_timetable(update, context):
    user_timetable=get_user_day_timetable(update.message.from_user.id)
    update.message.reply_text(user_timetable if user_timetable != None else USER_FREE_DAY, reply_markup=timetable_markup(0))

def proceed_news(update, context):
    update.message.reply_text('Пока не реализовано')

def get_user_notify_mode(user_id):
    user_timetable=""
    with engine.connect() as conn:
        result = conn.execute(sqlalchemy.text(f"SELECT send_msg_time FROM users.usergroup WHERE user_id = :uid"), uid = user_id)
        if result.rowcount == 0:
            return None
        else:
            send_msg_time = result.fetchone()['send_msg_time']
            if (send_msg_time == None) or (not send_msg_time):
                return 0
            return 1


def proceed_settings_start(update, context):
    
    update.message.reply_text('Настроечки', reply_markup=settings_markup(get_user_notify_mode(update.message.from_user.id))) #IN THE FUTETRE, CHANGE NUM IN MARKUP AS SELECT FROM DB GET USER RECIEVING MESSAGES MODE
    #update.message.reply_text('Введите желаемое время\nФормат: hh:mm', reply_markup=ForceReply())
    return ONE

def proceed_settings(update, context):
    try:
        with engine.begin() as conn:
            job_id = ''
            user_time = datetime.datetime.strptime(update.message.text,'%H:%M')
            group_names_query = conn.execute(sqlalchemy.text("SELECT job_id FROM users.usergroup WHERE user_id=:uid AND job_id IS NOT NULL"), uid=update.message.from_user.id)
            if group_names_query.rowcount != 0:
                old_job_id = group_names_query.fetchone()['job_id']
                call(f'at -r {old_job_id}', shell=True)
            job_id = create_at_job(update.message.from_user.id, update.message.text)
            conn.execute(sqlalchemy.text("UPDATE users.usergroup SET (send_msg_time, job_id) = (:smt,:jid) WHERE user_id=:uid"), uid=update.message.from_user.id, smt=user_time, jid=int(job_id))
            update.message.reply_text(f'Теперь вы будете ежедневно оповещаться в {update.message.text}', reply_markup=menu_keyboard_markup)
            return ConversationHandler.END

    except Exception as e: #Ignored, becasue of INSERT ON CONFLICT
        logger.info(str(e))

def create_at_job(user_id, time):
    job_id = None
    tmp = tempfile.NamedTemporaryFile(mode='r+t')
    cmd = f'echo \"python3 send_daily.py {user_id}\" | at -m {time}'
    call(cmd, shell=True, stderr=tmp)
    tmp.seek(0)
    for line in tmp:
        if 'job' in line:
            job_id = line.split()[1]
    tmp.close()
    return job_id

def cancel_user_notifications(update, context):
    try:
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("UPDATE users.usergroup SET (send_msg_time, job_id) = (NULL,NULL) WHERE user_id=:uid"), uid=update.from_user.id)
        update.edit_message_text(text='Больше не присылаю уведомлений')
    except: pass
    return ConversationHandler.END


def button(update, context):
    query = update.callback_query

    query.answer()
    chosen_time = int(query.data)
  
    if chosen_time == 1:
        current_user_timetable = get_user_week_timetable(query.from_user.id)
        if not current_user_timetable:
            query.edit_message_text(text='Занятий на этой неделе больше не будет')
            query.edit_message_reply_markup(timetable_markup(chosen_time))
        else:
            msg_to_user = ""
            for msg in current_user_timetable: #current_user_timetable[:-1]
                msg_to_user+=msg + "\n\n"
            #for msg in current_user_timetable[:-1]:
                #query.bot.send_message(query.message.chat_id, msg) #new message for each day
            #query.bot.send_message(query.message.chat_id, current_user_timetable[-1], reply_markup=timetable_markup(chosen_time))
            #query.bot.delete_message(query.message.chat_id, query.message.message_id)
            query.edit_message_text(text=msg_to_user)
            query.edit_message_reply_markup(timetable_markup(chosen_time))
        #query.edit_message_text(text=current_user_timetable if current_user_timetable != None else USER_FREE_DAY)
    elif chosen_time == 0:
        current_user_timetable = get_user_day_timetable(query.from_user.id)
        query.edit_message_text(text=current_user_timetable if current_user_timetable != None else USER_FREE_DAY)
        query.edit_message_reply_markup(timetable_markup(chosen_time))

def get_current_week():
    if datetime.date.today().month < 6 and datetime.date.today().month > 2:
        return datetime.date.today().isocalendar()[1] - datetime.date(datetime.date.today().year,9,1).isocalendar()[1] + 1
    else:
        return datetime.date.today().isocalendar()[1] - datetime.date(datetime.date.today().year,9,1).isocalendar()[1] + 1

def settings_controller(update, context):
    query = update.callback_query

    query.answer()
    chosen_property = int(query.data)
  
    if chosen_property == 1: #SEND AT SPECIFIC TIME
        return send_user_request_specific_time(query, context)
    elif chosen_property == 0: #DON'T SEND NOTIFICATIONS TO USER
        return cancel_user_notifications(query, context)

def send_user_request_specific_time(update, context):
    update.edit_message_text(text='Введите желаемое время\nФормат: hh:mm')
    #update.message.reply_text('Введите желаемое время\nФормат: hh:mm', reply_markup=ForceReply())
    return TWO

def main():
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater("***REMOVED***", use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start), MessageHandler(Filters.text('Сменить группу') & (~Filters.command), change_user_group)],

        states={
            ONE: [MessageHandler(Filters.text & (~Filters.command), gender)],
            TWO: [CallbackQueryHandler(select_group)]
        },

        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    settings_conversation_handler = ConversationHandler(
        entry_points=[MessageHandler(Filters.text('Настройки бота') & (~Filters.command), proceed_settings_start)],
        states={
            ONE: [CallbackQueryHandler(settings_controller)],
            TWO: [MessageHandler(Filters.text & (~Filters.command), proceed_settings)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    timetable_handler = MessageHandler(Filters.text('Расписание') & (~Filters.command), proceed_timetable)
    news_handler = MessageHandler(Filters.text('Новости') & (~Filters.command), proceed_news)
    #settings_handler = MessageHandler(Filters.text('Настройки бота') & (~Filters.command), proceed_settings_start)
    dp.add_handler(conv_handler)
    dp.add_handler(timetable_handler)
    dp.add_handler(news_handler)
    dp.add_handler(settings_conversation_handler)
    dp.add_handler(CallbackQueryHandler(button))
    #dp.add_handler(MessageHandler(Filters.text, handle_users_reply))
    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
