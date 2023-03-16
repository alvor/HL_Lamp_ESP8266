import gc
import machine, ds2406, onewire, ds18x20, hl
import network, ntptime
import uasyncio as asyncio
from ubinascii import hexlify as b2h
from ubinascii import unhexlify as h2b
import json
import time
import sys
from nanoweb import Nanoweb, send_file

devs = []
H_OK = 'HTTP/1.1 200 OK\r\n'
MAXTEMP = 60
maxtemp = 0
ssid = json.loads(open('wifipsw.psw').read()).get('ssid')
pswd = json.loads(open('wifipsw.psw').read()).get('pswd')

sta = network.WLAN(network.STA_IF)

hl_timezone = 7
ow_pin = 2
ds18_delay = 730

Ch1Time=((8,00),(20,00))
Ch2Time=((8,15),(19,45))

ow = onewire.OneWire(machine.Pin(ow_pin))
ds18 = ds18x20.DS18X20(ow)

_ds24 = hl._ow_2406('sv1',ow,b'128a9bb4000000fc')
_ds18 = hl._ow_18x20('tmp',ow,b'28ff300676200286')
_lmps = [hl_2406_ch("Lamp 1",_ds24,0),hl_2406_ch("Lamp 2",_ds24,0)]

naw = Nanoweb()
naw.assets_extensions += ('ico', 'png',)
_DIR = '/_web/'
naw.STATIC_DIR = _DIR
gc.threshold(2000)

def get_time():
    _date = time.localtime()[0:4]
    _time = time.localtime()[3:6]
    return (
        '{}-{:02d}-{:02d}'.format(*_date),
        '{:02d}:{:02d}:{:02d}'.format(*_time),
    )

async def api_ls(rq):
    try:
        uos.chdir(rq.url.split('?chdir=')[1])
    except:
        pass
    else:
        pass
    await rq.write(H_OK)
    await rq.write("Content-Type: application/json\r\n\r\n")
    await rq.write('{"files": [%s]}' % ', '.join(
        '"' + f + '"' for f in ['..']+sorted(uos.listdir())
    ))

#TODO добавить куррент дир
async def api_send_response(rq, code=200, message="OK"):
    await rq.write("HTTP/1.1 %i %s\r\n" % (code, message))
    await rq.write("Content-Type: application/json\r\n\r\n")
    await rq.write('{"status": true}')



async def api_status(rq):
    await rq.write(H_OK)
    await rq.write("Content-Type: application/json\r\n\r\n")
    mem_free = gc.mem_free()
    date_str, time_str = get_time()
    await rq.write(json.dumps({
        "date": date_str,
        "time": time_str,
        "mem_free": mem_free,
        "currdir": uos.getcwd()
    }))

async def api_lmp(rq):
    await rq.write(H_OK)
    await rq.write("Content-Type: application/json\r\n\r\n")
    await rq.write(json.dumps({
        "ch1_time": Ch1Time,
        "ch2_time": Ch2Time,
    }))

async def api_eval(rq):
    await rq.write(H_OK)
    await rq.write("Content-Type: application/json\r\n\r\n")
    ev=rq.url.split('ev=')[1]
    print(ev)
    ev=eval(ev)
    await rq.write(json.dumps(ev))
    gc.collect()

async def keep_connect():
    while True:
        if sta.active():
            if not sta.isconnected():
                try:
                    sta.connect(ssid, pswd)
                except:
                    print('Can not connected')
                else:
                    print("Connected")
            else:
                print(sta.ifconfig())
                try:
                    #TODO From where time?
                    ntptime.NTP_DELTA = ntptime.NTP_DELTA - hl_timezone * 3600
                    ntptime.settime()
                    print('Time set ok')
                except:
                    print('Time set errors')
                else:
                    print('Time : ', time.localtime())
        else:
            sta.active(False)
            sta.active(True)
        await asyncio.sleep(600)


async def system_loop():
    crcErLv = 0
    while True:
        try:
            ds18.convert_temp()
            await asyncio.sleep_ms(ds18_delay)
            max_tmp = 0
            for i in tmps:
                try:
                    tmp = ds18.read_temp(h2b(i))
                    max_tmp = max(max_tmp, tmp)
                except:
                    crcErLv += 1
                    print('CRC Er', crcErLv)
                    if crcErLv > 15: crcErLv = 15
                else:
                    print('Tmp ', i, ' : ', tmp)
                    crcErLv -= 2
                    if crcErLv < 0: crcErLv = 0
                if (max_tmp > MAXTEMP) or (crcErLv > 5):
                    for j in lmps:
                        ds24.turn((j), 1, 1)
                        print('Lmp {} off'.format(j))
                else:
                    print('All ok. Tmp ', i, ' : ', tmp)
                    print('Mem free:',gc.mem_free())
                    schedule()
            print("Max temp : ", max_tmp)
        except:
            print('DS18b20 Error')
        gc.collect()
        await asyncio.sleep(5)

def schedule():
    lt=time.localtime()[3:5]
    Ch1 = Ch1Time[0] < lt < Ch1Time[1]
    Ch2 = Ch2Time[0] < lt < Ch2Time[1]
    ds2406.turn(lmps[0], int(Ch1), int(Ch2))

async def index(rq):
    await rq.write(H_OK + '\r\n')
    for i in ['header','index','footer']:
        print('/%s.html' % (_DIR+i))
        await send_file(rq, '/%s.html' % (_DIR+i), )

async def lmp(rq):
    await rq.write(H_OK + '\r\n')
    for i in ['header', 'lmp', 'footer']:
        print('/%s.html' % (_DIR + i))
        await send_file(rq, '/%s.html' % (_DIR + i), )


async def assets(rq):
    await rq.write(H_OK)
    args = {}
    filename = rq.url.split('/')[-1]
    if filename.endswith('.png'):
        args = {'binary': True}
    await rq.write("\r\n")
    await send_file(
        rq,
        '/%s/%s' % (_DIR, filename),
        **args,
    )

async def files(rq):
    await rq.write(H_OK + '\r\n')
    for i in ['header','files','footer']:
        await send_file(rq, '/%s.html' % (_DIR+i), )


async def api_download(rq):
    await rq.write(H_OK)

    filename = rq.url[len(rq.route.rstrip("*")) - 1:].strip("/")
    await rq.write("Content-Type: application/octet-stream\r\n")
    await rq.write("Content-Disposition: attachment; filename=%s\r\n\r\n" % filename)
    await send_file(rq, filename)


async def upload(rq):
    if rq.method != "PUT":
        raise HttpError(rq, 501, "Not Implemented")

    bytesleft = int(rq.headers.get('Content-Length', 0))

    if not bytesleft:
        await rq.write("HTTP/1.1 204 No Content\r\n\r\n")
        return

    output_file = rq.url[len(rq.route.rstrip("*")) - 1:].strip("\/")
    tmp_file = output_file + '.tmp'

    try:
        with open(tmp_file, 'wb') as o:
            while bytesleft > 0:
                chunk = await rq.read(min(bytesleft, 64))
                o.write(chunk)
                bytesleft -= len(chunk)
            o.flush()
    except OSError as e:
        raise HttpError(rq, 500, "Internal error")

    try:
        uos.remove(output_file)
    except OSError as e:
        pass

    try:
        uos.rename(tmp_file, output_file)
    except OSError as e:
        raise HttpError(rq, 500, "Internal error")

    await api_send_response(rq, 201, "Created")

naw.routes = {
    '/': index,
    '/lamp':lmp,
    '/assets/*': assets,
    '/api/status': api_status,
    '/api/upload/*': upload,
    '/api/ls*': api_ls,
    '/api/eval*': api_eval,
    '/api/download/*': api_download,
    '/api/lmp': api_lmp,
    '/files': files,
}

loop = asyncio.get_event_loop()
loop.create_task(keep_connect())
loop.create_task(system_loop())
loop.create_task(naw.run())
loop.run_forever()
