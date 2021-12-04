import sqlalchemy
import pandas
import requests.exceptions, requests
from get_user_token import get_user_token

engine = sqlalchemy.create_engine('postgresql://***REMOVED***:***REMOVED***@192.144.37.124:5432/demo')
ttcell = requests.get('https://api.ciu.nstu.ru/v1.0/data/simple/tt_cell',
                                      cookies={'NstuSsoToken': get_user_token()})

try:
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text('DELETE FROM test.test_table; INSERT INTO test.test_table (data) VALUES (:vl); DELETE FROM test.tt_cell; INSERT INTO test.tt_cell SELECT * FROM test.fill_tt_cell_view;'), vl=ttcell.text)
except Exception as e:
    print(e)
    with engine.begin() as conn:
        file = open('./sql/create/tt_cell.sql')
        conn.execute(sqlalchemy.text(file.read()))
        conn.execute(sqlalchemy.text('DELETE FROM test.test_table; INSERT INTO test.test_table (data) VALUES (:vl); DELETE FROM test.tt_cell; INSERT INTO test.tt_cell SELECT * FROM test.fill_tt_cell_view;'), vl=ttcell.text)
print('done')