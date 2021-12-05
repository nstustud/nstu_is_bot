import datetime
import logging
import os
import tempfile
from subprocess import call

import pandas
import sqlalchemy
from rapidfuzz import fuzz, process
from telegram import (ForceReply, InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyKeyboardMarkup)
from telegram.ext import (CallbackQueryHandler, CommandHandler,
                          ConversationHandler, Filters, MessageHandler,
                          Updater)
from transliterate import translit

import misc.config as config
from misc.constants import (BACK, CLAIM_USER_GROUP_HANDLER, CREDIT_WEEK,
                            DAY_SCHEDULE, DISABLED_NOTIFICATION,
                            ENABLED_NOTIFICATION, FORCED_BACK, MENU_BUTTONS,
                            OFFSET_TIME_SETTINGS_HANDLER,
                            SCHEDULE_MENU_HANDLER, SET_USER_GROUP_HANDLER,
                            SETTINGS_CONTROLLER_HANDLER,
                            SPECIFIC_TIME_SETTINGS_HANDLER,
                            SPECIFIC_WEEK_SCHEDULE,
                            SPECIFIC_WEEK_SCHEDULE_HANDLER,
                            SPECIFY_SEND_MSG_TIME,
                            SPECIFY_SEND_MSG_TIME_OFFSET,
                            START_SETTINGS_HANDLER, TIMETABLE_NAME,
                            USER_FREE_DAY, WEEK_SCHEDULE, NEWS_BUTTON_TEXT
                            )

menu_keyboard_markup = ReplyKeyboardMarkup(
    MENU_BUTTONS,
    one_time_keyboard=False,
    resize_keyboard=True
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

days_dict = {1: 'Пн', 2: 'Вт', 3: 'Ср', 4: 'Чт', 5: 'Пт', 6: 'Сб', 7: 'Вс'}

engine = sqlalchemy.create_engine(config.db_connection_string)

settings_state_dict = {}

def TIMETABLE_ROW_TEMPLATE(row):
    return f"[{row['pair_number']}] {row['starttime']}-{row['endtime']} {'[' + row['tsw_name'] + '] ' if row['tsw_name'] is not None else ''} {row['classname']} {row['rooms']} {row['teacher1']} {row['teacher2']}\n"


def start(update, context):
    update.message.reply_text(
        'Привет. Я бот-помощник студента НГТУ \n'
        'Отправьте /cancel если хотите прервать общение.\n\n'
        'Введите вашу группу', reply_markup=ForceReply())
    return CLAIM_USER_GROUP_HANDLER


def timetable_markup(chosen_time):
    keyboard = [[InlineKeyboardButton(f"Расписание на текущий день {'✅' if chosen_time == DAY_SCHEDULE else ''}", callback_data=DAY_SCHEDULE)],
                [InlineKeyboardButton(f"Расписание на оставшуюся неделю {'✅' if chosen_time == WEEK_SCHEDULE else ''}", callback_data=WEEK_SCHEDULE)],
                [InlineKeyboardButton(f"Расписание на выбранную неделю {'✅' if chosen_time == SPECIFIC_WEEK_SCHEDULE else ''}", callback_data=SPECIFIC_WEEK_SCHEDULE)]]
    return InlineKeyboardMarkup(keyboard)


def settings_markup(chosen_parameter):
    keyboard = [[InlineKeyboardButton(f"{'Отключить' if chosen_parameter == ENABLED_NOTIFICATION else 'Включить' if chosen_parameter == DISABLED_NOTIFICATION else 'ОШИБКА'} ежедневную отправку расписания", callback_data=DISABLED_NOTIFICATION if chosen_parameter == DISABLED_NOTIFICATION else ENABLED_NOTIFICATION)]]
    return InlineKeyboardMarkup(keyboard)


def notification_settings_markup():
    keyboard = [[InlineKeyboardButton("Выбрать время отправки расписания", callback_data=SPECIFY_SEND_MSG_TIME)],
                [InlineKeyboardButton("Выбрать времени оповещения относительно первой пары", callback_data=SPECIFY_SEND_MSG_TIME_OFFSET)],
                [InlineKeyboardButton("Назад", callback_data=FORCED_BACK)]
                ]
    return InlineKeyboardMarkup(keyboard)


def weeks_num_markup():
    keyboard = [[InlineKeyboardButton("1", callback_data='WEEK1'), InlineKeyboardButton("2", callback_data='WEEK2'), InlineKeyboardButton("3", callback_data='WEEK3')],
                [InlineKeyboardButton("4", callback_data='WEEK4'), InlineKeyboardButton("5", callback_data='WEEK5'), InlineKeyboardButton("6", callback_data='WEEK6')],
                [InlineKeyboardButton("7", callback_data='WEEK7'), InlineKeyboardButton("8", callback_data='WEEK8'), InlineKeyboardButton("9", callback_data='WEEK9')],
                [InlineKeyboardButton("10", callback_data='WEEK10'), InlineKeyboardButton("11", callback_data='WEEK11'), InlineKeyboardButton("12", callback_data='WEEK12')],
                [InlineKeyboardButton("13", callback_data='WEEK13'), InlineKeyboardButton("14", callback_data='WEEK14'), InlineKeyboardButton("15", callback_data='WEEK12')],
                [InlineKeyboardButton("16", callback_data='WEEK16'), InlineKeyboardButton("17", callback_data='WEEK17'), InlineKeyboardButton("18", callback_data='WEEK18')],
                [InlineKeyboardButton("Назад", callback_data=DAY_SCHEDULE)]]
    return InlineKeyboardMarkup(keyboard)


def get_true_groups_name(input, group_names):
    score = process.extract(translit(input.upper(), 'ru'), group_names, scorer=fuzz.partial_ratio, limit=5)
    return list(map(list, zip(*score)))[0]


def gender(update, context):
    try:
        with engine.begin() as conn:
            group_names_query = conn.execute(sqlalchemy.text("SELECT name FROM test.group_names"))
            group_names = [row['name'] for row in group_names_query]

            true_group = get_true_groups_name(update.message.text, group_names)
            keyboard = []
            for group in true_group:
                keyboard.append([InlineKeyboardButton(group, callback_data=group)])
            keyboard.append([InlineKeyboardButton('Другая группа', callback_data='Другая группа')])
            update.message.reply_text('Выберите группу', reply_markup=InlineKeyboardMarkup(keyboard))
            return SET_USER_GROUP_HANDLER

    except Exception as e:
        logger.info(str(e))


# todo: delete old notification setting if user changes his group
def select_group(update, context):
    query = update.callback_query
    if query.data == 'Другая группа':
        query.message.delete()
        change_user_group(query, context)
        return CLAIM_USER_GROUP_HANDLER
    try:
        query.answer()
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("INSERT INTO users.usergroup (user_id, group_name) VALUES (:u_id, :gn) ON CONFLICT (user_id) DO UPDATE SET group_name = :gn"), u_id=query.from_user.id, gn=query.data)
            # We resend message with markup, because callback_query can't send menu keyboard as markup
            query.message.reply_text(f'Ваша группа {update.callback_query.data}!\nПоздравляю вас\n', reply_markup=menu_keyboard_markup)
            query.message.delete()

    except sqlalchemy.exc.IntegrityError:   # Ignored, becasue of INSERT ON CONFLICT
        query.message.reply_text('Вы уже есть тут, шо вам еще надо?', reply_markup=menu_keyboard_markup)
        query.message.delete()
    return ConversationHandler.END


def change_user_group(update, context):
    update.message.reply_text('Введите имя группы:', reply_markup=ForceReply())
    return CLAIM_USER_GROUP_HANDLER


def cancel(update, context):
    update.message.reply_text('Не пытайся лезть сюда. Фу')
    return CLAIM_USER_GROUP_HANDLER


def get_user_day_timetable(user_id):
    user_timetable = ''
    with engine.connect() as conn:
        current_week = get_current_week()
        if current_week < 19:
            week_check_str = 'AND ((is_odd = -1 AND week18 = True) OR (is_odd = 0))' if current_week == 18 else f'AND week{current_week} = true'
            result = conn.execute(sqlalchemy.text(f"SELECT * FROM {TIMETABLE_NAME} WHERE group_name IN (SELECT group_name FROM users.usergroup WHERE user_id = :uid LIMIT 1) AND day = (select extract(isodow from now())) {week_check_str} ORDER BY starttime"), uid=user_id)
            if result.rowcount == 0:
                return None
            else:
                for row in result:
                    user_timetable += TIMETABLE_ROW_TEMPLATE(row)
    return user_timetable


def get_user_week_timetable(user_id, week_to_check, is_rest_week):
    rest_week_sql = f'AND ((day = EXTRACT(isodow from {config.SQL_NOW}) AND endtime > to_char({config.SQL_NOW}, \'HH24:MI\')) OR (day>EXTRACT(isodow from {config.SQL_NOW})))'
    week_check_str = 'AND ((is_odd = -1 AND week18 = True) OR (is_odd = 0))' if week_to_check == 18 else f'AND week{week_to_check} = true'

    with engine.connect() as conn:
        result = pandas.read_sql(sqlalchemy.text(f"SELECT * FROM {TIMETABLE_NAME} WHERE group_name IN (SELECT group_name FROM users.usergroup WHERE user_id = :uid LIMIT 1) {week_check_str} {rest_week_sql if is_rest_week == True else ''} ORDER BY day, starttime"), conn, params={'uid': user_id})
    days_timetable_list = []
    days = result[['day']].groupby('day').count()
    for day_idx in days.index:
        current_day_text = ""
        current_day_timetable = result[result['day'] == day_idx]
        current_day_text += days_dict[day_idx] + '\n'
        for _index, row in current_day_timetable.iterrows():
            current_day_text += TIMETABLE_ROW_TEMPLATE(row)
        days_timetable_list.append(current_day_text)
    return days_timetable_list


def proceed_timetable(update, context):
    user_timetable = get_user_day_timetable(update.message.from_user.id)
    update.message.reply_text(f"Сейчас {get_current_week()} неделя\n\n" + user_timetable if user_timetable is not None else USER_FREE_DAY, reply_markup=timetable_markup(DAY_SCHEDULE))
    return SCHEDULE_MENU_HANDLER


def proceed_news(update, context):
    update.message.reply_text(
        'В разработке.\nНаберитесь терпения.',
        reply_markup=menu_keyboard_markup
    )


def get_user_notify_mode(user_id):
    if user_id not in settings_state_dict:
        with engine.connect() as conn:
            result = conn.execute(
                sqlalchemy.text(
                    "SELECT send_msg_time, offset_time \
                    FROM users.usergroup WHERE user_id = :uid"
                ),
                uid=user_id
            )
            if result.rowcount == 0:
                return None
            else:
                tmp = result.fetchone()
                send_msg_time = tmp['send_msg_time']
                offset_time = tmp['offset_time']
                if ((send_msg_time is None) or (not send_msg_time)) and ((offset_time is None) or (not offset_time)):
                    settings_state_dict[user_id] = DISABLED_NOTIFICATION
                    return DISABLED_NOTIFICATION
                settings_state_dict[user_id] = ENABLED_NOTIFICATION
                return ENABLED_NOTIFICATION
    else:
        return settings_state_dict[user_id]


def proceed_settings_start(update, context):
    update.message.reply_text('Настроечки', reply_markup=settings_markup(get_user_notify_mode(update.message.from_user.id)))    # IN THE FUTETRE, CHANGE NUM IN MARKUP AS SELECT FROM DB GET USER RECIEVING MESSAGES MODE
    return START_SETTINGS_HANDLER


def proceed_specific_time_settings(update, context):
    try:
        with engine.begin() as conn:
            job_id = ''
            user_time = datetime.datetime.strptime(update.message.text, '%H:%M')
            group_names_query = conn.execute(sqlalchemy.text("SELECT job_id FROM users.usergroup WHERE user_id=:uid AND job_id IS NOT NULL"), uid=update.message.from_user.id)
            if group_names_query.rowcount != 0:
                old_job_id = group_names_query.fetchone()['job_id']
                call(f'at -r {old_job_id}', shell=True)
            job_id = create_at_job(update.message.from_user.id, update.message.text)
            conn.execute(sqlalchemy.text("UPDATE users.usergroup SET (send_msg_time, job_id, offset_time) = (:smt,:jid, NULL) WHERE user_id=:uid"), uid=update.message.from_user.id, smt=user_time.time(), jid=int(job_id))
            update.message.reply_text(f'Теперь вы будете ежедневно оповещаться в {update.message.text}', reply_markup=settings_markup(ENABLED_NOTIFICATION))
            settings_state_dict[update.message.from_user.id] = ENABLED_NOTIFICATION
            return START_SETTINGS_HANDLER
    except Exception as e:
        logger.info(str(e))


def get_offset_date(user_id, input_time):
    try:
        current_study_week = get_current_week()
        with engine.begin() as conn:
            date_string = ''
            week_of_year = datetime.date.today().isocalendar()[1]
            file = open('./sql/select/next_first_pair.sql')
            next_first_pair_query = conn.execute(sqlalchemy.text(file.read()), uid=user_id, week_num=current_study_week)
            if next_first_pair_query.rowcount != 0:
                tmp = next_first_pair_query.fetchone()
                week_of_year = datetime.date.today().isocalendar()[1]
                week = week_of_year - current_study_week + tmp['week']
                first_pair_time = datetime.datetime.strptime(tmp['starttime'], '%H:%M')
                notify_time = datetime.datetime.min + (first_pair_time - input_time)
                actual_date = datetime.datetime.fromisocalendar(datetime.date.today().isocalendar()[0], week, tmp['day']).replace(hour=notify_time.hour, minute=notify_time.minute)
                date_string = actual_date.strftime('%H:%M %d.%m.%Y')
    except Exception:
        pass
    return date_string


def proceed_offset_time_settings(update, context):
    try:
        user_time = datetime.datetime.strptime(update.message.text, '%H:%M')
        date_string = get_offset_date(
            user_id=update.message.from_user.id,
            input_time=user_time
        )
        with engine.begin() as conn:
            job_id = ''
            old_job_id_query = conn.execute(sqlalchemy.text("SELECT job_id FROM users.usergroup WHERE user_id=:uid AND job_id IS NOT NULL"), uid=update.message.from_user.id)
            if old_job_id_query.rowcount != 0:
                old_job_id = old_job_id_query.fetchone()['job_id']
                call(f'at -r {old_job_id}', shell=True)
            job_id = create_at_job(update.message.from_user.id, date_string)
            conn.execute(sqlalchemy.text("UPDATE users.usergroup SET (send_msg_time, job_id, offset_time) = (NULL,:jid,:offset_time) WHERE user_id=:uid"), uid=update.message.from_user.id, offset_time=user_time, jid=int(job_id))
            update.message.reply_text(f'Теперь вы будете ежедневно оповещаться за {update.message.text} до пары', reply_markup=settings_markup(ENABLED_NOTIFICATION))
            settings_state_dict[update.message.from_user.id] = ENABLED_NOTIFICATION
            return START_SETTINGS_HANDLER
    except Exception as e:
        logger.info(str(e))


def create_at_job(user_id, time):
    job_id = None
    tmp = tempfile.NamedTemporaryFile(mode='r+t')
    cmd = f'echo \"python3 {os.getcwd()}/send_daily.py {user_id}\" | at -m {time}'
    call(cmd, shell=True, stderr=tmp)
    tmp.seek(0)
    for line in tmp:
        if 'job' in line:
            job_id = line.split()[1]
    tmp.close()
    return job_id


def cancel_user_notifications(query, context):
    try:
        with engine.begin() as conn:
            job_id_query = conn.execute(sqlalchemy.text("SELECT job_id FROM users.usergroup WHERE user_id=:uid AND job_id IS NOT NULL"), uid=query.from_user.id)
            if job_id_query.rowcount != 0:
                old_job_id = job_id_query.fetchone()['job_id']
                call(f'at -r {old_job_id}', shell=True)
            conn.execute(sqlalchemy.text("UPDATE users.usergroup SET (send_msg_time, job_id, offset_time) = (NULL,NULL,NULL) WHERE user_id=:uid"), uid=query.from_user.id)
            settings_state_dict[query.from_user.id] = DISABLED_NOTIFICATION
            query.edit_message_text(text='Больше не присылаю уведомлений')
            query.edit_message_reply_markup(settings_markup(DISABLED_NOTIFICATION))
    except Exception as e:
        print(e)
        pass
    return START_SETTINGS_HANDLER


def button(update, context):
    query = update.callback_query
    chosen_time = query.data
    current_week = get_current_week()
    query.answer()

    if chosen_time == WEEK_SCHEDULE:
        current_user_timetable = get_user_week_timetable(query.from_user.id, current_week, is_rest_week=True)
        if not current_user_timetable:
            query.edit_message_text(text='Занятий на этой неделе больше не будет')
            query.edit_message_reply_markup(timetable_markup(chosen_time))
        else:
            msg_to_user = 'Сейчас ' + (CREDIT_WEEK if current_week == 18 else f'{current_week} неделя\n\n')
            for msg in current_user_timetable:
                msg_to_user += msg + "\n\n"
            query.edit_message_text(text=msg_to_user)
            query.edit_message_reply_markup(timetable_markup(chosen_time))
    elif chosen_time == DAY_SCHEDULE:
        current_user_timetable = get_user_day_timetable(query.from_user.id)
        query.edit_message_text(text=f"Сейчас {current_week} неделя\n\n" + current_user_timetable if current_user_timetable is not None else USER_FREE_DAY)
        query.edit_message_reply_markup(timetable_markup(chosen_time))
    elif chosen_time == SPECIFIC_WEEK_SCHEDULE:
        query.edit_message_text(text=f"Сейчас {current_week} неделя\n\nВыберите номер недели:")
        query.edit_message_reply_markup(weeks_num_markup())
        return SPECIFIC_WEEK_SCHEDULE_HANDLER
    return SCHEDULE_MENU_HANDLER


def get_current_week():
    if datetime.date.today().month < 8 and datetime.date.today().month > 2:
        return datetime.date.today().isocalendar()[1] - datetime.date(datetime.date.today().year, 9, 1).isocalendar()[1] + 1
    else:
        week_num = datetime.date.today().isocalendar()[1] - datetime.date(datetime.date.today().year, 9, 1).isocalendar()[1] + 1
        return week_num


def settings_controller(update, context):
    query = update.callback_query
    query.answer()
    if query.data == DISABLED_NOTIFICATION:     # SEND AT SPECIFIC TIME
        query.edit_message_text(text="Ну выбери ты уже пункт меню\n")
        query.edit_message_reply_markup(notification_settings_markup())
        return SETTINGS_CONTROLLER_HANDLER
    elif query.data == ENABLED_NOTIFICATION:    # DON'T SEND NOTIFICATIONS TO USER
        return cancel_user_notifications(query, context)


def norification_settings_controller(update, context):
    query = update.callback_query
    query.answer()
    if query.data == SPECIFY_SEND_MSG_TIME:
        return send_user_request_of_specific_time(query, context)
    elif query.data == SPECIFY_SEND_MSG_TIME_OFFSET:
        return send_user_request_of_offset_time(query, context)
    elif query.data == FORCED_BACK:
        query.edit_message_text(text="Настроечки туть")
        query.edit_message_reply_markup(settings_markup(get_user_notify_mode(query.from_user.id)))
        return START_SETTINGS_HANDLER
    elif query.data == BACK:
        query.edit_message_text(text="Ну выбери ты уже пункт меню\n")
        query.edit_message_reply_markup(notification_settings_markup())
        return SETTINGS_CONTROLLER_HANDLER


def send_user_request_of_specific_time(query, context):
    query.edit_message_text(text='Введите желаемое время\nФормат: hh:mm')
    query.edit_message_reply_markup(InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data=BACK)]]))
    return SPECIFIC_TIME_SETTINGS_HANDLER


def send_user_request_of_offset_time(query, context):
    query.edit_message_text(text='Введите offset времени перед парами\nФормат: hh:mm')
    query.edit_message_reply_markup(InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data=BACK)]]))
    return OFFSET_TIME_SETTINGS_HANDLER


def fallback(update, context):
    context.update_queue.put(update)
    return ConversationHandler.END


def proceed_specific_week_schedule(update, context):
    try:
        query = update.callback_query
        # I think this solution will be faster that subscribing SPECIFIC_WEEK_SCHEDULE_HANDLER to button
        if query.data == DAY_SCHEDULE:
            button(update, context)
        else:
            query.answer()
            chosen_week = int(query.data[len('WEEK'):])     # delete substr WEEK
            current_user_timetable = get_user_week_timetable(query.from_user.id, chosen_week, is_rest_week=False)
            if not current_user_timetable:
                query.edit_message_text(text=f'Занятий на {chosen_week} неделе не будет')
                query.edit_message_reply_markup(InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data=DAY_SCHEDULE)]]))
            else:
                msg_to_user = (CREDIT_WEEK + '\n\n') if chosen_week == 18 else f'{chosen_week} неделя\n\n'
                for msg in current_user_timetable:
                    msg_to_user += msg + "\n\n"
                query.edit_message_text(text=msg_to_user)
                query.edit_message_reply_markup(InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data=DAY_SCHEDULE)]]))
        return SCHEDULE_MENU_HANDLER
    except Exception:
        pass


def main():
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater(config.bot_token, use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # we'll put handlers to the misc folder in the future.
    schedule_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(Filters.text('Расписание') & (~Filters.command), proceed_timetable)],
        states={
            SCHEDULE_MENU_HANDLER: [CallbackQueryHandler(button, pattern=r"\w*SCHEDULE$")],
            SPECIFIC_WEEK_SCHEDULE_HANDLER: [CallbackQueryHandler(proceed_specific_week_schedule, pattern=fr'^(WEEK([1-9]|1[0-8])|{DAY_SCHEDULE})$')]
        },
        fallbacks=[MessageHandler(Filters.text([item for sublist in MENU_BUTTONS for item in sublist]), fallback)]
    )

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler(['start', 'restart'], start), MessageHandler(Filters.text(['Сменить группу']) & (~Filters.command), change_user_group)],

        states={
            CLAIM_USER_GROUP_HANDLER: [MessageHandler(Filters.text & (~Filters.command), gender)],
            SET_USER_GROUP_HANDLER: [CallbackQueryHandler(select_group)]
        },

        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(Filters.text([item for sublist in MENU_BUTTONS for item in sublist]), cancel)]
    )

    settings_conversation_handler = ConversationHandler(
        entry_points=[MessageHandler(Filters.text(['Настройки бота']) & (~Filters.command), proceed_settings_start)],
        states={
            START_SETTINGS_HANDLER: [CallbackQueryHandler(settings_controller)],
            SETTINGS_CONTROLLER_HANDLER: [CallbackQueryHandler(norification_settings_controller)],
            SPECIFIC_TIME_SETTINGS_HANDLER: [MessageHandler(Filters.text & (~Filters.command), proceed_specific_time_settings), CallbackQueryHandler(norification_settings_controller)],
            OFFSET_TIME_SETTINGS_HANDLER: [MessageHandler(Filters.text & (~Filters.command), proceed_offset_time_settings), CallbackQueryHandler(norification_settings_controller)]
        },
        fallbacks=[MessageHandler(Filters.text([item for sublist in MENU_BUTTONS for item in sublist]), fallback)]
    )

    news_handler = MessageHandler(Filters.text(NEWS_BUTTON_TEXT) & (~Filters.command), proceed_news)
    dp.add_handler(conv_handler)
    dp.add_handler(schedule_conv_handler)
    dp.add_handler(settings_conversation_handler)
    dp.add_handler(news_handler)
    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
