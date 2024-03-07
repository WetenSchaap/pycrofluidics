import sys
from ctypes import *
from array import array
import pathlib
import time
import datetime
import json
import pycrofluidics.common as common

class MUXelve:
    '''
    Overarching class controlling Elveflow MUX distributor 1/12
    '''
    def __init__(self, elveflowDLL = None, elveflowSDK = None, deviceName = None):
        """
        Create Pelve device class.

        Parameters
        ----------
        elveflowDLL : str (path), optional
            Path to the Elveflow DLL, which you have downloaded seperately. Defaults to whatever is set in the config file. Note that if you supply the DLL manually here, you //also// have to supply the SDK manually.
        elveflowSDK : str (path), optional
            Path to the Elveflow SDK for python, which you have downloaded seperately. Defaults to whatever is set in the config file. Note that if you supply the SDK manually here, you //also// have to supply the DLL manually.
        deviceName : str, optional
            Check readme on how to get this, requires external software (NI MAX). Defaults to whatever is set in the config file.
        """
        if type(deviceName) != str and deviceName != None:
            raise TypeError("deviceName should be supplied as string or left at default")
        if any( [elveflowDLL!=None, elveflowSDK!= None] ):
            if ( not pathlib.Path(elveflowDLL).exists() ) or ( not pathlib.Path(elveflowSDK).exists() ):
                raise FileNotFoundError("I could not find the given paths to the Elveflow DLL and/or Python SDK")
        self.deviceName = deviceName
        self.ELVEFLOW_DLL = elveflowDLL
        self.ELVEFLOW_SDK = elveflowSDK
        self.loadDLL()

    def open(self, auto_home = True, verbose = False):
        """
        Open connection to MUX distributor. 
        
        Parameters
        ----------
        autoHome : bool, optional 
            Before usage, device should always be homed. Set to True to do this automatically when connection is established. By default True
        verbose : bool, optional
            Whether to talk about things. Defaults False
        """
        if self.deviceName == None:
            self.deviceName = common.read_config("mux_name")
        self.Instr_ID = c_int32()
        error = self.ef.MUX_DRI_Initialization(
            self.deviceName.encode('ascii'),
            byref(self.Instr_ID)
        )
        common.raiseEFerror(error,'Initialize connection to MUX distributor')
        if verbose:
            print(f"Error code: {error}, Instrument ID: {self.Instr_ID.value}")
        if auto_home:
            self.home()
    
    def close(self):
        error = self.ef.MUX_DRI_Destructor( self.Instr_ID )
        common.raiseEFerror(error,'Closing connection to MUX distributor')

    def home( self, start_channel = 1 ):
        """
        Home the MUX. Needed before ever using it. Will return to position 1 by default. In this home function I wobble arround after to make sure it is set up correctly (not //always// the case.) This homing action is BLOCKING!
        
        Parameters
        ----------
        autoHome : bool, optional 
            Before usage, device should always be homed. Set to True to do this automatically when object is created. By default True
        """
        Answer=(c_char*40)() # it needs to be able to give a generic reply, even if it is not used.
        error = self.ef.MUX_DRI_Send_Command(
            self.Instr_ID.value,
            0,
            Answer,
            40
        ) # length is set to 40 to contain the whole Serial Number, which is a possible answer.
        # print('Answer',Answer.value) # This will just return Home
        common.raiseEFerror(error,'Homing MUX distributor')
        self.wait_for_valve_movement( timeout=10 )
        self.set_valve(1, blocking = True)
        self.set_valve(12, blocking = True)
        self.set_valve(start_channel, blocking = True)

    def set_valve(self, valve_index, rotation_direction = 0, blocking = False):
        """
        Move to inputted valve location. Will not do anything if you are allready at given location (build-in behaviour is to make a full lap for some reason).

        Parameters
        ----------
        valve_index: int, between 1 and 12
            Set valve to turn to.
        rotation_direction: int, any of [0,1,2], optional
            Set direction in which the switch turns. 0 is fastest, 1 is clockwise, 2 is counterclockwise.
        blocking: bool, optional
            Whether to block while MUX is turning. Defaults to False.
        """
        valve_index = int( valve_index )
        if not (0 < valve_index < 13):
            raise ValueError("Choose a valve index between 1 and 12")
        if self.get_valve() == valve_index: # am allready there, bye.
            return valve_index
        valve_index_i32 = c_int32( valve_index ) #convert to c_int32
        error = self.ef.MUX_DRI_Set_Valve(
            self.Instr_ID.value,
            valve_index_i32,
            rotation_direction,
        )
        common.raiseEFerror(error,f'Switching to MUX valve with index {valve_index}')
        if blocking:
            self.wait_for_valve_movement()
        if (self.get_valve() != valve_index ) and (self.get_valve() != 0):
            raise ConnectionError(f"Failed to set MUX to correct location: set to {valve_index}, but found at {self.get_valve()}")
        return valve_index

    def get_valve(self):
        """
        Get current position of valve. If 0 is returned, valve is currently busy!
        """
        valve = c_int32( -1 ) # This will contain the valve later
        error = self.ef.MUX_DRI_Get_Valve(
            self.Instr_ID.value,
            byref(valve)
        ) # Number 1-12. it returns 0 if valve is busy.
        common.raiseEFerror(error,f'gettting valve position of MUX')
        return int(valve.value)
    
    def wait_for_valve_movement(self, timeout = 5):
        '''Block execution while valve is moving. Timeout is in seconds.'''
        current_valve = 0
        t0 = time.time()
        while current_valve == 0:
            current_valve = self.get_valve()
            if time.time() - t0 > timeout:
                raise ConnectionError("Critical hardware error: valve movement has timed out")
        return True

    def loadDLL(self):
        """
        Load Elveflow DLL and acompanying Python SDK.
        """
        if self.ELVEFLOW_DLL != None or self.ELVEFLOW_SDK != None:
            sys.path.append(self.ELVEFLOW_DLL)
            sys.path.append(self.ELVEFLOW_SDK)
        else:
            common.add_elveflow_to_path()
        import Elveflow64 as ef
        self.ef = ef

    def __enter__(self, auto_home = True, verbose = False):
        self.open( auto_home = auto_home, verbose = verbose)
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        #Exception handling here, if an error occurs in the with block
        self.close()