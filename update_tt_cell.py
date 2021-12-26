import sqlalchemy
import requests
import misc.config as config
from get_user_token import get_user_token

engine = sqlalchemy.create_engine(config.db_connection_string)
ttcell = requests.get(
    url='https://api.ciu.nstu.ru/v1.0/data/simple/tt_cell',
    cookies={'NstuSsoToken': get_user_token(config.nstu_login, config.nstu_password)}
)

try:
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text('DELETE FROM test.test_table; INSERT INTO test.test_table (data) VALUES (:vl); DELETE FROM test.tt_cell; INSERT INTO test.tt_cell SELECT * FROM test.fill_tt_cell_view ON CONFLICT DO NOTHING;'), vl=ttcell.text)
except Exception as e:
    print(e)
    with engine.begin() as conn:
        file = open('./sql/create/tt_cell.sql')
        conn.execute(sqlalchemy.text(file.read()))
        conn.execute(sqlalchemy.text('DELETE FROM test.test_table; INSERT INTO test.test_table (data) VALUES (:vl); DELETE FROM test.tt_cell; INSERT INTO test.tt_cell SELECT * FROM test.fill_tt_cell_view;'), vl=ttcell.text)
print('done')
