import logging
import sys
# path to roonapi folder
sys.path.append('\\pyRoon\\pyRoonLib\\roonapi')
import roonapi, discovery, constants
import time, os
import json
import socket
import subprocess, shlex
# from constants import LOGGER
import logging
from logging.handlers import RotatingFileHandler

def main():
    global roon
    roon = None
    global logger
    logger = logging.getLogger('RoonEndpointAssistant')
    global settings
    settings = None
    global dataFolder
    dataFolder = None
    global dataFile
    dataFile = None
    global inDebugger
    inDebugger = getattr(sys, 'gettrace', None)
    global appinfo
    appinfo = {
        "extension_id": "sonnabend.roon.egvolume:2",
        "display_name": "EG Controller",
        "display_version": "1.0.0",
        "publisher": "sonnabend",
        "email": "",
    }
    # configure file logging
    file_handler = RotatingFileHandler('RoonEndpointAssistant.log', maxBytes=1e5, backupCount=2)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(fmt='%(asctime)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    # configure console logging
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    try:
        logger.setLevel(level=logging.DEBUG)
        # global roon
        # global settings
        loadSettings()
        # authorize if necessary
        try:
            if settings["core_id"].strip() == "" or settings["token"] == "":
                authorize()
        except:
            authorize()
        # connect to Roon core
        roon = connect(settings["core_id"], settings["token"])
        settings["core_id"] = roon.core_id
        settings["token"] = roon.token
        # subscribe to status notifications
        # roon.register_state_callback(state_change_callback)
        hostname = socket.gethostname()
        roon.register_volume_control("1", hostname, volume_control_callback, 0, "incremental")
        buttons = []
        try:
            buttons = settings["buttons"]
            for button in buttons:
                roon.register_source_control(button["id"], button["label"], source_control_callback, True, button["initial_state"])
        except:
            pass
        while True:
            time.sleep(0.1)
            pass
    finally:
        #finally, save settings
        if not (settings is None):
            saveSettings()

def connect(core_id, token):
    logger.info("in connect\n  core_id: %s\n  token: %s" % (core_id,token))
    global appinfo
    try:
        discover = discovery.RoonDiscovery(core_id, dataFolder)
        logger.info("discover object: %s" % discover)
        server = discover.first()
        logger.info("server object: %s:%s" % (server[0], server[1]))
        roon = roonapi.RoonApi(appinfo, token, server[0], server[1], True)
        logger.info("roon object: %s" % roon)
        return roon
    except:
        return None
    finally:
        discover.stop()

def authorize():
    logger.info("authorizing")
    global appinfo
    global settings

    logger.info("discovering servers")
    discover = discovery.RoonDiscovery(None)
    servers = discover.all()
    logger.info("discover: %s\nservers: %s" % (discover, servers))

    logger.info("Shutdown discovery")
    discover.stop()

    logger.info("Found the following servers")
    logger.info(servers)
    apis = [roonapi.RoonApi(appinfo, None, server[0], server[1], False) for server in servers]

    auth_api = []
    while len(auth_api) == 0:
        logger.info("Waiting for authorisation")
        time.sleep(1)
        auth_api = [api for api in apis if api.token is not None]

    api = auth_api[0]

    logger.info("Got authorisation")
    logger.info("   host ip: " + api.host)
    logger.info("   core name: " + api.core_name)
    logger.info("   core id: " + api.core_id)
    logger.info("   token: " + api.token)
    # This is what we need to reconnect
    settings["core_id"] = api.core_id
    settings["token"] = api.token

    logger.info("leaving authorize with settings: %s" % settings)

    logger.info("Shutdown apis")
    for api in apis:
        api.stop()


def state_change_callback(event, changed_ids):
    global roon
    """Call when something changes in roon."""
    logger.info("state_change_callback event:%s changed_ids: %s\n" % (event, changed_ids))
    for zone_id in changed_ids:
        zone = roon.zones[zone_id]
        logger.info("zone_id:%s zone_info: %s" % (zone_id, zone))

def source_control_callback(control_key, event, data):
    global roon
    logger.info("source_control_callback control_key: %s event: %s data: %s\n" % (control_key, event, data))
    command = None
    param = None
    new_state = event
    try:
        #get data from settings
        button = next((button for button in settings["buttons"] if button["id"] == control_key), None)
        if event == "standby":
            command = button["command_off"]
            param = button["param_off"]
            new_state = "selected"
        else:
            command = button["command_on"]
            param = button["param_on"]
            new_state = "standby"
        if not command == None:
            command = '"%s" %s' % (command,param)
            logger.info("running command %s\n" % (command))
            subprocess.run(shlex.split(command))
    except:
        logger.info("Error running command/params. Check config for proper entries.")
    roon.update_source_control(control_key, new_state)

def volume_control_callback(control_key, event, value):
    global roon
    logger.info("volume_control_callback control_key: %s event: %s value: %s\n" % (control_key, event, value))
    command = None
    param = None
    try:
        #get command and param from settings
        if value == 1:
            command = settings["command_volume_up"]["command"]
            param = settings["command_volume_up"]["param"]
        elif value == -1:
            command = settings["command_volume_down"]["command"]
            param = settings["command_volume_down"]["param"]
        elif event == "set_mute":
            command = settings["command_volume_mute"]["command"]
            param = settings["command_volume_mute"]["param"]
        #format command and param and pass to subprocess.run
        if not command == None:
            command = '"%s" %s' % (command,param)
            logger.info("running command %s\n" % (command))
            subprocess.run(shlex.split(command))
    except:
        logger.info("Error running command/params. Check config for proper entries.")
    roon.update_volume_control(control_key, 0, False)

def loadSettings():
    global dataFolder
    global dataFile
    global settings
    logger.info("running from %s" % __file__)
    # logger.info(os.environ)
    if ("_" in __file__): # running in temp directory, so not from PyCharm
        dataFolder = os.path.join(os.getenv('APPDATA'), 'pyRoonEGVolume')  #os.path.abspath(os.path.dirname(__file__))
    else:
        dataFolder = os.path.dirname(__file__)
    dataFile = os.path.join(dataFolder , 'settings.dat')
    logger.info("using dataFile: %s" % dataFile)
    if not os.path.isfile(dataFile):
        f = open(dataFile, 'a').close()
    try:
        f = open(dataFile, 'r')
        settings = json.load(f)
    except:
        settings = json.loads('{}')
    f.close()
    return settings

def saveSettings():
    global settings
    data = json.dumps(settings, indent=4)
    if (not data  == '{}') and (os.path.isfile(dataFile)):
        f = open(dataFile, 'w')
        f.write(data)
        f.close()

if __name__ == "__main__":
    main()