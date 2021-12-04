from requests import post as req_post
def get_user_token():
    headers = {'Content-Type': 'application/json',
                   'X-OpenAM-Username': "***REMOVED***",
                   'X-OpenAM-Password': "***REMOVED***"
                  }
    r = req_post('https://login.nstu.ru/ssoservice/json/authenticate', headers=headers)
    return r.json()['tokenId']