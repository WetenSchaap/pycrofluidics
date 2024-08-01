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
    8007 : 'ESI software seems to have connection with Device, close ESI before continuing in Python',
    2 : "Unknown error from stopping remote mode"
}

def read_config(key:str):
    """
    Read value from config file
    """
    config_file = where_is_the_config_file()
    yo = yaml.YAML(typ='safe')
    config = yo.load(config_file)
    return config[key]

def write_config(key:str, value:str):
    """
    Add key-value pair to config file.
    """
    assert type(key) == type(value) == str, 'Config key and values should always be strings'
    config_file = where_is_the_config_file()
    yo = yaml.YAML(typ='safe')
    config = yo.load(config_file)
    config[key] = value
    # Force block style
    yo.default_flow_style = False
    yo.indent(mapping=2, sequence=4, offset=2)
    yo.dump(config,config_file)

def add_elveflow_to_path():
    """
    Add Elveflow SDK and DLL to path, based on config file.
    """
    sys.path.append(read_config("elveflow_dll"))
    sys.path.append(read_config("elveflow_sdk"))

def raiseEFerror(error:int, action:str = 'Elveflow command'):
    """Raise an error with errorcode, and give the reason if it is known."""
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
    config_dir = pathlib.Path( platformdirs.user_config_dir(appname = pycrofluidics.APPNAME, 
                                                            appauthor = pycrofluidics.APPAUTHOR) )
    config_dir.mkdir(parents=True,exist_ok=True)
    return config_dir

def where_is_the_config_file() -> str:
    """Return the path to the config file, containing default config like device names."""
    config_dir = where_is_the_config_dir()
    config_file = config_dir / "config.yaml"
    if not config_file.exists():
        config_file.touch()
    return config_file