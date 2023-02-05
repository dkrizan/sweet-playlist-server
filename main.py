import json
import os
import requests
import uuid
import time
from bottle import route, response, redirect, run, template

email = os.getenv('USERNAME')
password = os.getenv('PASSWORD')

if email is None or password is None:
    raise Exception("Env variables USERNAME or PASSWORD not set.")

HOST = "localhost"
PORT = 8888
API_HOST = 'api.sweet.tv'

UA = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:105.0) Gecko/20100101 Firefox/105.0'
HEADERS = {
    'Host': API_HOST, 'user-agent': UA, 'accept': 'application/json, text/plain, */*', 'accept-language': 'cs',
    'x-device': '1;22;0;2;3.2.57', 'origin': 'https://sweet.tv', 'dnt': '1', 'referer': 'https://sweet.tv/'
}
SHARED_DATA = {
    'device': {
        'type': 'DT_Web_Browser',
        'application': {
            'type': 'AT_SWEET_TV_Player'
        },
        'model': UA,
        'firmware': {
            'versionCode': 1,
            'versionString': '3.2.57'
        },
        'supported_drm': {'widevine_modular': True},
        'screen_info': {
            'aspectRatio': 6,
            'width': 1366,
            'height': 768
        }
    }
}

# Load saved token
try:
    with open("./token.json", 'r') as openfile:
        token_data = json.load(openfile)
except (FileNotFoundError, json.decoder.JSONDecodeError):
    token_data = None

stream_id = None
catchup = ' catchup="append" catchup-source="?utc={utc}&utcend={utcend}",'
input_stream = "#KODIPROP:inputstream=inputstream.adaptive\n#KODIPROP:inputstream.adaptive.manifest_type=hls\n" \
               "#KODIPROP:mimetype=application/x-mpegURL\n"


def login():
    _json = SHARED_DATA
    _json["device"]["uui"] = str(uuid.uuid4())
    _json["email"] = email
    _json["password"] = password
    req = requests.post("https://" + API_HOST + "/SigninService/Email.json", json=_json, headers=HEADERS).json()
    if req["result"] == "OK":
        req["expires_in"] = time.time() + int(req["expires_in"])
        json_object = json.dumps(req, indent=4)
        with open("./token.json", "w") as outfile:
            global token_data
            token_data = json_object
            outfile.write(json_object)
        print("Logged successfully.")
        return req['access_token']
    else:
        raise Exception("Invalid credentials or service unavailable.")


def get_token():
    global token_data
    # if no token data are stored
    if token_data is None:
        return login()
    else:
        if token_data["expires_in"] > time.time():
            return token_data["access_token"]
        else:
            _json = SHARED_DATA
            _json["device"]["uui"] = str(uuid.uuid4())
            _json["refresh_token"] = token_data['refresh_token']
            req = requests.post(
                "https://" + API_HOST + "/AuthenticationService/Token.json", json=_json, headers=HEADERS
            ).json()
            if req["result"] == "OK":
                return req["access_token"]


def channels(reload=False):
    access_token = get_token()
    if not reload:
        try:
            with open("./channels.json", "r") as _openFile:
                return json.load(_openFile)
        except (FileNotFoundError, json.decoder.JSONDecodeError):
            pass

    headers = HEADERS
    headers["authorization"] = "Bearer " + access_token
    _categories = {}
    _channels = {}
    _body = {
        'need_epg': False, 'need_list': True, 'need_categories': True, 'need_offsets': False, 'need_hash': False,
        'need_icons': False, 'need_big_icons': False
    }
    req = requests.post("https://" + API_HOST + "/TvService/GetChannels.json", json=_body, headers=headers).json()
    if req["status"] == "OK":
        for c in req["categories"]:
            _categories[c["id"]] = c["caption"]
        for ch in req["list"]:
            _channels[str(ch["id"])] = {
                "name": ch["name"].replace(" HD", ""), "logo": ch["icon_url"],
                "group": _categories[ch["category"][0]]
            }
        json_object = json.dumps(_channels, indent=4)
        with open("./channels.json", "w") as _outfile:
            _outfile.write(json_object)
    else:
        print(req["result"])
    return _channels


def get_stream(_channel_id):
    global stream_id
    try:
        access_token = get_token()
        headers = HEADERS
        headers["authorization"] = "Bearer " + access_token
        if stream_id != "":
            try:
                requests.post(
                    "https://" + API_HOST + "/TvService/CloseStream.json",
                    json={"stream_id": int(stream_id)},
                    headers=headers
                ).json()
            except:
                pass
        data = {
            'without_auth': True,
            'channel_id': int(_channel_id),
            'accept_scheme': ['HTTP_HLS'],
            'multistream': True
        }
        req = requests.post("https://" + API_HOST + "/TvService/OpenStream.json", json=data, headers=headers).json()
        if req["result"] == "OK":
            stream_id = str(req["stream_id"])
            return "https://" + req["http_stream"]["host"]["address"] + req["http_stream"]["url"]
    except:
        pass
    return "https://sledovanietv.sk/download/noAccess-cs.m3u8"


@route("/channels")
def show_channels():
    return template(json.dumps(channels()))


@route("/play/<channel_id>")
def play(channel_id):
    stream = get_stream(channel_id)
    response.content_type = "application/vnd.apple.mpegurl"
    return redirect(stream)


@route("/playlist")
def playlist():
    t = ""
    for x, y in channels().items():
        t += '#EXTINF:-1 provider="Sweet TV" group-title="' + y["group"] + '"' + ' tvg-logo="' + y["logo"] + '"'
        t += catchup + y["name"] + "\n" + input_stream + "http://" + str(HOST) + ":" + str(PORT) + "/play/" + str(x) + "\n"
    if t != "":
        t = "#EXTM3U\n" + t
    response.content_type = 'text/plain; charset=UTF-8'
    return t


if __name__ == '__main__':
    run(host=HOST, port=PORT, reloader=False)