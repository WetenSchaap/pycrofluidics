import sys
from ctypes import *
from array import array
import pathlib
import datetime
import json
import pycrofluidics.common as common

class Pelve:
    '''
    Overarching class controlling Elveflow OB1-Mk4
    '''
    def __init__( self, elveflowDLL = None, elveflowSDK = None, deviceName = None, deviceRegulators = [0,0,0,0] ):
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
        deviceRegulators: list of 4 ints, optional
            Select which regulators are installed in the OB1, numbers correspond to pressure ranges, run printRegulatorTypes() to see what pressures correspond to what numbers. In Mk4 device, set all to 0. Defaults to [0,0,0,0].
        """
        if type(deviceName) != str and deviceName != None:
            raise TypeError("deviceName should be supplied as string or left at default")
        if type(deviceRegulators) != list:
            printRegulatorTypes()
            raise TypeError("Give deviceRegulators as a list of 4 integers, see table above")
        if len(deviceRegulators) != 4:
            printRegulatorTypes()
            raise TypeError("Give deviceRegulators as a list of 4 integers, see table above")
        if (any([type(i)!=int for i in deviceRegulators])):
            printRegulatorTypes()
            raise TypeError("Give integer value corresponding to regulator type from table above.")
        if (any([i<0 for i in deviceRegulators]) or any([i>5 for i in deviceRegulators])):
            printRegulatorTypes()
            raise ValueError("Unknown device regulator selected, choose from list above")
        if any( [elveflowDLL!=None, elveflowSDK!= None] ):
            if ( not pathlib.Path(elveflowDLL).exists() ) or ( not pathlib.Path(elveflowSDK).exists() ):
                raise FileNotFoundError("I could not find the given paths to the Elveflow DLL and/or Python SDK")
        self.deviceName = deviceName
        self.deviceRegulators = deviceRegulators
        self.ELVEFLOW_DLL = elveflowDLL
        self.ELVEFLOW_SDK = elveflowSDK
        self.insideRemote = False
        self.confPIDs = [False,False,False,False]
        self.runningPIDs = [False,False,False,False]
        self.loadDLL()

    def open(self):
        """
        Open connection with Elveflow device.
        """
        if self.deviceName == None:
            self.deviceName = common.read_config("ob1_name")
        self.Instr_ID = c_int32()
        error = self.ef.OB1_Initialization(
            self.deviceName.encode('ascii'),
            self.deviceRegulators[0],
            self.deviceRegulators[1],
            self.deviceRegulators[2],
            self.deviceRegulators[3],
            byref(self.Instr_ID)
        )
        common.raiseEFerror(error,'Initialize connection to OB1')
    
    def close(self):
        """
        Close connection with Elveflow device
        """
        if self.insideRemote:
            try:
                self.stopRemote() # Gracefully shut down, also if there is a control loop running.
            except ConnectionError as e:
                # If not gracefull, force the issue
                print('Remote process could not be stopped ({e}), but closing connection anyway.')
        error = self.ef.OB1_Destructor(self.Instr_ID)
        common.raiseEFerror(error,'Closing connection to OB1')

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

    def loadCallibration(self,path = None):
        """
        Load existing callibration for pressure channels. Loads from default calibration file, or optionally from user-supplied path.

        Parameters
        ----------
        path : str (path), optional
            Path to callibration file (must be json!). Defaults to the standard callibration location, as given when creating this Pelve object.
        """
        if path is None:
            path = common.read_config("ob1_callibration")
        elif type(path) != str:
            raise TypeError("Give callibration file path as string")
        elif not pathlib.Path(path).exists():
            raise ValueError(f"No callibration file found at '{path}', please set different path or perform callibration using Pelve.performCallibration()")
        self.calib = loadCalibration(path)

    def performCallibration(self,path = None):
        """
        Perform callibration of pressure channels, and save data for next time. If no path is supplied, the callibration will be saved to the default location. If a callibration data file allready exists (at the user-given location or the default), the original file will be renamed with creation date at the end as a backup.

        Parameters
        ----------
        path : str (path), optional
            Path where to save callibration file (will be a .json file!). Defaults to the standard callibration location, see docs.
        """
        if self.insideRemote:
            raise ValueError("Remote loop is running; only inside loop functions allowed!")
        if path is None:
            path = common.read_config("ob1_callibration")
        elif type(path) != str:
            raise TypeError("Give callibration file path as string")
        print("This will take ~5 minutes. Longer means kernel died. Make sure the channels are properly plugged.")
        # Perform new callibration
        self.calib = (c_double*1000)() # This is where callibration is stored!
        error = self.ef.OB1_Calib(self.Instr_ID.value, self.calib, 1000)
        common.raiseEFerror(error,'Performing callibration')
        # first backup old callibration if it exists, before overwriting with new data!
        if pathlib.Path(path).exists():
            oldCal = pathlib.Path(path)
            age =  datetime.datetime.fromtimestamp( oldCal.stat().st_mtime, tz=datetime.timezone.utc)
            agestring = age.strftime(r'%Y%m%d')
            oldCal.rename( str(oldCal.absolute()) + "." + agestring )
            print("Old callibration is backed up") 
        # and save
        saveCalibration(self.calib, path)
        print("New callibration was performed and saved.")

    def setPressure(self,channel,pressure):
        """
        Set pressure goal in channel

        Parameters
        ----------
        channel : int
            channel to set pressure in.
        pressure : float
            goal pressure to set to.
        """
        if self.insideRemote:
            raise ValueError("Remote loop is running; only inside loop functions allowed!")
        channel = self._channelCheck( int(channel) )
        pressure = c_double( float(pressure) ) # convert to c_double
        error = self.ef.OB1_Set_Press( self.Instr_ID.value, channel, pressure, byref(self.calib),1000)
        common.raiseEFerror(error,'Setting pressure')

    def getPressure(self,channel):
        """
        Read pressure at channel

        Parameters
        ----------
        channel : int
            Channel number, between 1 and 4
        """
        if self.insideRemote:
            raise ValueError("Remote loop is running; only inside loop functions allowed!")
        channel = self._channelCheck(channel)
        pressure = c_double()
        error = self.ef.OB1_Get_Press(self.Instr_ID.value, channel, 1, byref(self.calib),byref(pressure), 1000) # Acquire_data=1 -> read all the analog values
        common.raiseEFerror(error,'Getting pressure')
        return pressure.value

    def setPressureBulk(self,pressures):
        """
        Set pressure of all channels in one go. If you want to set the pressure of 1 channel, use setPressure

        WARNING: NOT FUNCTIONAL - Something goes wrong with ctypes here. The DLL expects a c_double, but I need to input 4 values. Not sure how to fix that. Giving one value will set only the first channel, sooooo. Ask stackOverflow or Elveflow (haha)?

        Parameters
        ----------
        pressures : list-like
            Pressure in mbar for each channel, with idx 0 being the first channel.
        """
        if self.insideRemote:
            raise ValueError("Remote loop is running; only inside loop functions allowed!")
        try: 
            pressures = list(pressures)
        except TypeError:
            raise TypeError("input pressures must be list-like")
        if len(pressures) != 4:
            raise ValueError("Exactly 4 Pressures need to be given here")
        pressuresArray = (c_double * len(pressures))(*pressures) # This magically converts data type
        
        firstArrayPoint = pressuresArray[0]
        lenghtOfPressureArray = c_int(len(pressures))
        error = self.ef.OB1_Set_All_Press( self.Instr_ID.value, byref(pressuresArray), byref(self.calib),4,1000)
        common.raiseEFerror(error,'Setting pressure')

    def addSensor(self,channel,sensorType,resolution=7,sensorDig=1,sensorIPACalib=0,sensorCustVolt=5.01):
        """
        Add sensor to device. Note that I assume the sensor is digital, 

        Parameters  
        ----------
        channel : int
            Channel at which sample is connected
        sensorType : int
            Type of sensor. Print options with printSensorTypes(). Probably its 4.
        resolution : int, optional
            Set resolution of sensor, see printSensorResolutions(), defaults to 7, the highest resolution with longest integration time.
        sensorDig: 0 or 1, optional
            If using a digital sensor set to 1. Defaults to 1.
        sensorIPACalib: 0 or 1, optional
            If calibration from IPA, set to 1, if water use 0. Defaults to 0.
        sensorCustVolt : float, between 5 and 25 (in units Volt), optional
            If using Custom sensor, set a voltage. Very probably not needed, but a value needs to be supplied nontheless. Defaults to 5.01.
        """
        if self.insideRemote:
            raise ValueError("Remote loop is running; only inside loop functions allowed!")
        channel = self._channelCheck(channel)
        if not 0 <= sensorType <= 14:
            printSensorTypes()
            raise ValueError("Sensor type between 0 and 14, see above for list.")
        if not 0 <= resolution <= 7:
            printSensorResolutions()
            raise ValueError("Sensor resolution between 0 and 7, see above for list.")
        sensorType = c_uint16( int( sensorType ) ) # convert to c_int32
        resolution = c_uint16( int( resolution ) ) # convert to c_uint16
        sensorDig = c_uint16( sensorDig ) # 1 for digital sensor (and 0 for analogue)
        sensorIPACalib = c_uint16( sensorIPACalib ) # if calibration from IPA, use 1, if water use 0.
        sensorCustVolt = c_double( sensorCustVolt ) # mandatory unused argument
        
        # The arguments for the next function are: 1. The OB1 ID obtained at its initialization. 2 Channel to which the sensor is attached. 3 Sensor type (see below). 4 Digital (1) or Analog (0) communication. - Calibration: IPA (1) or H20 (0). - Resolution bits (see below). - Voltage for custom analog sensors, from 5 to 25V.
        error = self.ef.OB1_Add_Sens( self.Instr_ID.value, channel, sensorType, sensorDig, sensorIPACalib, resolution, sensorCustVolt) 
        common.raiseEFerror(error,'Connecting to sensor')

    def getSensorData(self, channel):
        """
        Get reading from sensor at channel, given in native units (so probably uL/min)

        Parameters
        ----------
        channel : int
            Channel number between 1 and 4

        Returns
        -------
        value : float
            sensor data reading.
        """
        if self.insideRemote:
            raise ValueError("Remote loop is running; only inside loop functions allowed!")
        channel = self._channelCheck(channel)
        data = c_double()
        acquireData1True0False = c_int32( 1 ) # required variable with no effect on digital sensors.
        error = self.ef.OB1_Get_Sens_Data(self.Instr_ID.value, channel, acquireData1True0False, byref(data))
        common.raiseEFerror(error,"Getting sensor data")
        return data.value
    
    def startRemote(self):
        """
        This will start "remote operation mode", a control loop in the background which automatically reads all sensors and regulators. No direct call to the OB1 can be made until the stopRemote function is called. Until then only function accessing this loop (remoteGetData, remoteSetTarget) are allowed.
        You want to use this remote loop, because you can give the system a PID control loop: instead of giving a target pressure, you can give a target sensor value (typically flow rate).
        """
        if self.insideRemote:
            raise ValueError("Remote loop is allready running and can thus not be started")
        error = self.ef.OB1_Start_Remote_Measurement(self.Instr_ID.value,byref(self.calib),1000)
        common.raiseEFerror(error,"Starting control loop")
        self.insideRemote = True # This tells other functions to stop working, since inside the loop you are only allowed to use 'inside loop functions'

    def stopRemote(self):
        """
        This will stop the "remote operation mode". Normal functions can be called as usual after running this.
        """
        if not self.insideRemote:
            raise ValueError("Remote loop is not running and can thus not be stopped")
        error = self.ef.OB1_Stop_Remote_Measurement(self.Instr_ID.value)
        common.raiseEFerror(error,"Stopping control loop")
        self.confPIDs = [False,False,False,False] # Reset these values
        self.runningPIDs = [False,False,False,False]
        self.insideRemote = False

    def remoteGetData(self,channel):
        """
        Read data from pressure channel and sensor (if present and connected) while inside the remote operation mode.

        Parameters
        ----------
        channel : int
            Channel number between 1 and 4

        Returns
        -------
        Pressure : float
            pressure reading
        SensorData : float
            sensor data reading
        """
        if not self.insideRemote:
            raise ValueError("Remote loop is not running, use regular getPressure/getSensorData functions")
        channel = self._channelCheck(channel)
        dataP = c_double()
        dataS = c_double()
        error = self.ef.OB1_Get_Remote_Data(self.Instr_ID.value,channel,byref(dataP),byref(dataS))
        common.raiseEFerror(error,"Getting data inside control loop")
        return dataP.value, dataS.value
        
    def remoteSetTarget(self, channel, target):
        """
        Set the target value of a channel in the remote loop. If NO PID is running, the target is the pressure in mbar, if a PID IS running, this sets the target sensor value (probably uL/min), towards which the PID is working.

        Parameters
        ----------
        channel : int
            Channel number between 1 and 4
        target : float
            target pressure/sensor value
        """
        if not self.insideRemote:
            raise ValueError("Remote loop is not running, start it firts to use PID-like processes.")
        channel = self._channelCheck(channel)
        target = c_double( target ) # convert to double
        error = self.ef.OB1_Set_Remote_Target(self.Instr_ID.value, channel, target)
        common.raiseEFerror(error,"Set target pressure/flow rate inside control loop")

    def remoteAddPID(self, channelP, channelS, P, I, run = True):
        """
        Initialize a PID loop between a pressure channel and a sensor, with proportional parameter 'P' and integral parameter 'I'. 
        If you do not know what a PID loop is, ask the internet before messing around here.

        Parameters
        ----------
        channelP : int
            Channel of pressure controller to control
        channelS : int
            Channel to which sensor is attached
        P : float
            proportional parameter
        I : float
            integral parameter
        run : bool, optional
            wheteher to immediately initialize PID loop, by default True
        """
        if not self.insideRemote:
            raise ValueError("PID can only be setup if remote loop is running")
        channelP = self._channelCheck(channelP)
        channelS = self._channelCheck(channelS)
        if type(run) != bool:
            raise TypeError("Give boolean run value")
        P = c_double( P )
        I = c_double( I )
        run = c_int32( int(run) )
        sensorID = self.Instr_ID.value # this is never set??? Set to same ID as OB1???
        error= self.ef.PID_Add_Remote(self.Instr_ID.value, channelP, sensorID, channelS, P, I , run)
        common.raiseEFerror(error,"Setup PID control loop")
        self.confPIDs[int(channelP.value)] = {'P':P.value,'I':I.value}
        self.runningPIDs[int(channelP.value)] = bool(int(run.value))

    def remotePausePID(self,channel):
        """Pause PID loop in channel"""
        run = False
        error = self._remoteStartstopPID(channel,run)
        common.raiseEFerror(error,"Pausing PID control loop")

    def remoteStartPID(self,channel):
        """Start PID loop in channel"""
        run = True
        error = self._remoteStartstopPID(channel,run)
        common.raiseEFerror(error,"Unpausing PID control loop")
    
    def _remoteStartstopPID(self,channel,run):
        """Start or stop PID control loop in channel"""
        channel = self._channelCheck(channel)
        if not type(self.confPIDs[int(channel.value)]) == dict:
            raise ValueError("No PID setup in this channel")
        run = c_int32( int(run) )
        error = self.ef.PID_Set_Running_Remote( self.Instr_ID.value, channel, run )
        self.runningPIDs[int(channel.value)] = bool(run.value)
        return error

    def remoteResetPID(self,channel):
        """Reset the PID loop in channel, start over, forgetting error, etc."""
        channel = self._channelCheck(channel)
        if not type(self.confPIDs[int(channel.value)]) == dict:
            raise ValueError("No PID setup in this channel")
        reset = c_int32( int(True) )
        P = c_double( self.confPIDs[int(channel.value)]["P"] )
        I = c_double( self.confPIDs[int(channel.value)]["I"] )
        error = self.ef.PID_Set_Params_Remote( self.Instr_ID.value, channel, reset, P, I )
        common.raiseEFerror(error,"Reset PID control loop")

    def remoteChangePID(self, channel, P, I, reset = True):
        """
        Change PID parameters of the loop controlling the pressure in a channel.

        Parameters
        ----------
        channel : int
            Pressure channel PID is acting on.
        P : float
            proportional parameter
        I : float
            integral parameter
        reset : bool, optional
            Whether to reset PID error etc., by default True
        """
        channel = self._channelCheck(channel)
        if not type(self.confPIDs[int(channel.value)]) == dict:
            raise ValueError("No PID setup in this channel")
        P = c_double( P )
        I = c_double( I )
        reset = c_int32( int(reset) )
        error = self.ef.PID_Set_Params_Remote( self.Instr_ID.value, channel, reset, P, I )
        common.raiseEFerror(error,"Changing PID control loop parameters")
        self.confPIDs[int(channel.value)]["P"] = P.value
        self.confPIDs[int(channel.value)]["I"] = I.value

    def _channelCheck(self,channel):
        """Check whether inputed channel number is valid, and return c datatype version of number"""
        if type(channel) == c_int32:
            return channel
        if not 1 <= channel <= 4:
            raise ValueError("Channel choice between 1 and 4")
        return c_int32( int( channel ) ) # convert to c_int32

    def getPressureUniversal(self, channel):
        """This function gets the pressure, without bothering you with details about remote operation mode and stuff like that."""
        if self.insideRemote:
            return self.remoteGetData(channel)[0]
        else:
            return self.getPressure(channel)
    
    def getFlowUniversal(self, channel):
        """This function gets the flow sensor readout in µl/min, without bothering you with details about remote operation mode and stuff like that."""
        if self.insideRemote:
            return self.remoteGetData(channel)[1]
        else:
            return self.getSensorData(channel)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        #Exception handling here, if an error occurs in the with block
        self.close()

def saveCalibration(calibrationData, location):
    """
    Saves the inputted calibrationdata as plain text at location. Note that callibrationData should be a c_double datatype!
    This native Python function replaces the Elveflow DLL function because that kept crashing for some reason.
    """
    try:
        calibrationData = list(calibrationData)
    except TypeError:
        raise TypeError("Callibration data is supposed to be a list-like object")
    with open(location, "wt") as f:
        json.dump(calibrationData,f,indent='\t')

def loadCalibration(location):
    """
    loads calibration data from plain text json file at location. Note that callibrationData needs to be generated with the saveCalibration function, not the Elveflow DLL function. Returns result as tuple of c_double!
    This native Python function replaces the Elveflow DLL function because that kept crashing for some reason.
    """
    if type(location) not in [str,]:
        raise TypeError("Input path should be str!")
    with open(location, "rt") as f:
        calibrationData = json.load(f)
    if len(calibrationData) != 1000:
        raise ValueError("Calibrationdata in file is misformed: should be list of 1000 elements, not {0} elements".format(len(calibrationData)))
    calibrationDataDouble = (c_double*len(calibrationData))(*calibrationData) # Prepare object
    #for i in range(len(calibrationData)):
    #    calibrationDataDouble[i] = c_double(calibrationData[i])
    return calibrationDataDouble

def printSensorTypes():
    print(
        "Z_sensor_type_none : 0\n"
        "Z_sensor _type_Flow_1_5_muL_min : 1\n"
        "Z_sensor _type_Flow_7_muL_min : 2\n"
        "Z_sensor _type_Flow_50_muL_min : 3\n"
        "Z_sensor _type_Flow_80_muL_min : 4\n"
        "Z_sensor _type_Flow_1000_muL_min : 5\n"
        "Z_sensor _type_Flow_5000_muL_min : 6\n"
        "Z_sensor_type_Press_70_mbar : 7\n"
        "Z_sensor _type_Press_340_mbar : 8\n"
        "Z_sensor _type_Press_1_bar : 9\n"
        "Z_sensor _type_Press_2_bar : 10\n"
        "Z_sensor _type_Press_7_bar : 11\n"
        "Z_sensor _type_Press_16_bar : 12\n"
        "Z_sensor _type_Level : 13\n"
        "Z_sensor_type_Custom : 14\n"
    )

def printRegulatorTypes():
    print(
        "| Regulator type (by range) | Code |\n"
        "| --- | --- |\n"
        "| Non-installed | 0 |\n"
        "| (0, 200) mbar | 1 |\n"
        "| (0, 2000) mbar | 2 |\n"
        "| (0, 8000) mbar | 3 |\n"
        "| (-1000, 1000) mbar | 4 |\n"
        "| (-1000, 6000) mbar | 5 |\n"
    )

def printSensorResolutions():
    print(
        "| Resolution | Code | Resolution | Code |\n"
        "| --- | --- |--- | --- |\n"
        "| 9 bits | 0 | 13 bits | 4 |\n"
        "| 10 bits | 1 | 14 bits | 5 |\n"
        "| 11 bits | 2 | 15 bits | 6 |\n"
        "| 12 bits | 3 | 16 bits | 7 |\n"
        "Higher resolution involves a longer integration time, with up to 75ms for a single measurement at 16bits."
    )