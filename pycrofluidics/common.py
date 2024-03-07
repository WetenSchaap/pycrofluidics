"""
Module containing functions and stuff different implemented devices and methods share, like the Elveflow error codes.
"""
import pycrofluidics
import sys
import platformdirs
import pathlib
import ruamel.yaml as yaml

ERRORCODES = {
    8000 : 'No Digital Sensor found',
    8001 : 'No pressure sensor compatible with OB1 MK3',
    8002 : 'No Digital pressure sensor compatible with OB1 MK3',
    8003 : 'No Digital Flow sensor compatible with OB1 MK3',
    8004 : 'No IPA config for this sensor',
    8005 : 'Sensor not compatible with AF1',
    8006 : 'No Instrument with selected ID',
    8007 : 'ESI software seems to have connection with Device, close ESI before continuing in Python'
}

def read_config(key):
    """
    Read value from config file
    """
    config_file = where_is_the_config_file()
    yo = yaml.YAML(typ='safe')
    config = yo.load(config_file)
    return config[key]

def add_elveflow_to_path():
    """
    Add Elveflow SDK and DLL to path, based on config file.
    """
    sys.path.append(read_config("elveflow_dll"))
    sys.path.append(read_config("elveflow_sdk"))

def raiseEFerror(error,action='Elveflow command'):
    if error == 0: 
        # This means no error
        return None
    elif abs(error) in ERRORCODES.keys():
        # Known error
        raise ConnectionError('{0} failed with errorcode {1} : {2}'.format(action,error,ERRORCODES[abs(error)]))
    else: 
        # Generic unknown error
        raise ConnectionError(f"{action} failed with errorcode {error} (not specified further)")

def where_is_the_config_dir():
    config_dir = pathlib.Path( platformdirs.user_config_dir(appname = pycrofluidics.APPNAME, appauthor = pycrofluidics.APPAUTHOR) )
    config_dir.mkdir(parents=True,exist_ok=True)
    return config_dir

def where_is_the_config_file():
    config_dir = where_is_the_config_dir()
    config_file = config_dir / "config.yaml"
    if not config_file.exists():
        config_file.touch()
    return config_file