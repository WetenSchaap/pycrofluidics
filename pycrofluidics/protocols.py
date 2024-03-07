"""
This file contains functions with convenient standard protocol things, like a sweeping over a range of pressures to see what the corresponding flow rate is.
"""

import time
import warnings
import numpy as np
import pandas as pd
import pathlib
import threading
import pycrofluidics

def injectVolume(pelve, muxelve, pressure_channel, flowrate_sensor_channel, inject_valve_channel, volume, stop_valve_channel = False, pressure = False, max_flow = 80, flow_rate = False, pollrate = 20):
    """
    Inject a specific volume into the chip using MUX. Do this at either fixed flowrate, fixed pressure or adaptive pressure. You can also use this as a threaded module and set the pressure/flow_rate externally, leaving this function to measure only (and switching off flow when volume has been injected.)

    parameters
    ----------
    pelve : pelve object
        object controlling ob1 pressure controller. I assume it is completely setup, and has sensors etc attached, connected, and set up. If you use flow-controlled option, make sure PID is allready setup.
    muxelve : muxelve object
        object controlling MUX distributor microfluidic switch
    pressure_channel : int
        Channel in which to control the pressure
    flowrate_sensor_channel : int
        Channel to which the flowrate sensor I use to measure volume is connected. Probably the same as pressure_channel
    inject_valve_channel : int
        Valve number from which I should take the thing to inject.
    volume : float (in µl)
        How much volume to inject.
    stop_valve_channel : int, optional
        At the end of an injection, I can switch of pressure, but it is safer to switch to a channel without connector, so there is no flowblack. And we are probably not using all 12 channels anyway. Set this to a unconnected plugged channel to do this. If left at False, I set the pressure/flow to zero at the end of an injection.
    pressure : float (in mbar), optional
        At what pressure to inject the liquid. If you leave at False, either set the pressure manually before starting this injection //or// set a goal flow_rate. Be carefull to not cause high flow rate!! This will cause unknown volumes to be injected > see maxflow
    max_flow : float (in µl/min), optional
        The flow sensor has a maxflow, above which it is no longer accurate, and the injected volume will be misjudged. Set this to the flowrate at which this function should warn the user. 
    flow_rate: float (in µl/min), optional
        At what flow rate to inject. If you leave at false, either set the pressure manually before starting this injection //or// set a goal pressure. Note that you need to initialize PID etc separately, this function does not do that for you.
    pollrate: float (in Hz), optional
        How often to check flow rate to estimate injected volume. Higher poll rate = better accuracy, but too fast will make things go wrong. I guessed 20 Hz as a good start, but not optimized.
    """
    # assume both objects are ready to go allready.
    if pressure and flow_rate:
        raise ValueError("Either set fixed pressure or fixed flow. Not both")
    # prep before turning on flow:
    volume_injected = 0 # µl
    loop_time = 1 / pollrate

    # setup pressure etc
    if pressure:
        pelve.setPressure(pressure_channel,pressure)
    elif flow_rate:
        pelve.remoteSetTarget(flowrate_sensor_channel,flow_rate)
    # setup MUX
    muxelve.set_valve(inject_valve_channel)
    while volume_injected < volume:
        ts = time.time()
        flow = pelve.getFlowUniversal(flowrate_sensor_channel)
        volume_injected += flow * (loop_time/60) # µl/min * ( 1 sec / 60 sec )
        if flow > max_flow: 
            # TODO: this depends on the flow sensor, and could be read out automatically probably... Fine for now
            warnings.warn(f"I detect flowrate is higher than can be measured accurately, currently {flow} µL/sec")
        te = time.time()
        sleeptime = loop_time - (te-ts)
        if sleeptime < 0:
            warnings.warn(f"I detect pollrate is set too high for communications (currently {pollrate} Hz, estimated max is {1/(te-ts)} Hz)")
        time.sleep(loop_time - (te-ts))
    if stop_valve_channel:
        muxelve.set_valve(stop_valve_channel)
    else:
        if pressure:
            pelve.setPressure(pressure_channel,0)
        elif flow_rate:
            pelve.remoteSetTarget(flowrate_sensor_channel,0)

def pressureSweep(pelveflow, channel, pressures, staticTime, acquisitionRate = 10, endAtZero = True):
    """
    Perform a pressure sweep with a specific channel, and keep track of the flow rates and pressures of all channels during this sweep

    Parameters
    ----------
    pelveflow : pjmsflow.Pelve
        Object controlling Elveflow pressure controller
    channel : int
        Number of channel to sweep
    pressures : list-like
        Pressures to visit. Will just do it in the order you specify. Typically: np.linspace(0,200,10) or something
    staticTime : float
        After you change the pressure, how long should I remain here and measure flows?
    acquisitionRate : float, optional
        How often to check sensors. Give in Hz, by default 10
    endAtZero : bool, optional
        Whether to drop pressure to zero at the end of the sweep, by default True

    Returns
    -------
    result : pandas.DataFrame
        Pandas dataframe containing all measured data. Matches output of acquireData().
    """
    for i in range(len(pressures)):
        p = pressures[i]
        pelveflow.setPressure(channel,p)
        data = acquireData(pelveflow, acquisitionRate, staticTime)
        if i == 0:
            result = data.copy()
        else:
            result = pd.concat([result,data],ignore_index=True)
    if endAtZero:
        pelveflow.setPressure(channel,0)
    return result

def acquireData(pelveflow, acquisitionRate=10, measureTime=60):
    """
    Acquire data: passively read sensor data from Elveflow device, both pressures and flow rates (if sensors are connected).

    Parameters
    ----------
    pelveflow : pjmsflow.Pelve
        Object controlling Elveflow pressure controller
    acquisitionRate : float, optional
        How often to check sensors. Give in Hz, by default 10. Note that this is approximate, more a guideline, due to the request taking some (variable) time, and me not thinking this is particularily important to be very accurate.
    measureTime : float, optional
        How long to monitor sensors, given in seconds, by default 60

    Returns
    -------
    result : pandas.DataFrame
        Pandas dataframe containing all measured data. Matches output of acquireData(). Columns are time, pressuredata, flowratedata, and the time it took to read all sensors (may be usefull for time-sensitive applications)
    """
    # WARNING: Sort of implicitly assumes 4 channels
    p = [False,False,False,False]
    s = [False,False,False,False]
    data = list()
    breakTime = 1/acquisitionRate
    measurementStart = time.time()
    measurementEnd = measurementStart + measureTime
    while True:
        startTime = time.time()
        if startTime > measurementEnd:
            break
        for i in range(4):
            try:
                p[i] =pelveflow.getPressure(i + 1)
            except ConnectionError:
                # Log it as a NaN, warn the user, and continnue as to not lose data
                warnings.warn(f"Pressure in channel {i+1} could not be read at least once.")
                p[i] = np.nan
        for i in range(4):
            try:
                s[i] =pelveflow.getSensorData(i + 1)
            except ConnectionError:
                # Log it as a NaN, warn the user, and continnue as to not lose data
                warnings.warn(f"Flowrate in channel {i+1} could not be read at least once.")
                s[i] = np.nan
        endTime = time.time()
        delta = endTime - startTime
        middleTime = startTime + (delta / 2)
        timeSinceStart = middleTime - measurementStart
        data.append([middleTime,timeSinceStart,*p,*s,delta])
        if startTime-time.time() < breakTime:
            time.sleep(breakTime)
        else:
            warnings.warn(f"Requested acquisition rate ({acquisitionRate} Hz) could not be reached, working at max possible rate instead (approx. {1 / delta} Hz)")
    result = pd.DataFrame(
        data=data,
        columns=[
            "Unix time (seconds)","Time (seconds)", "Pressure Ch. 1 (mbar)", "Pressure Ch. 2 (mbar)", "Pressure Ch. 3 (mbar)", "Pressure Ch. 4 (mbar)", "Flow Ch. 1 (ul/min)", "Flow Ch. 2 (ul/min)", "Flow Ch. 3 (ul/min)", "Flow Ch. 4 (ul/min)", "measuring time (seconds)", 
        ]
    )
    return result

def acquireDataCont(pelveflow, savePath, acquisitionRate=10, measureTime=60):
    # Like aquireData but with a continues writing to the savefile, so an error or something does not throw away the data.
    # WARNING: Sort of implicitly assumes 4 channels
    if type(savePath) == str:
        savePath = pathlib.Path(savePath)
    if savePath.exists():
        raise FileExistsError("File allready exists")
    columns=[
        "Unix time (seconds)","Time (seconds)", "Pressure Ch. 1 (mbar)", "Pressure Ch. 2 (mbar)", "Pressure Ch. 3 (mbar)", "Pressure Ch. 4 (mbar)", "Flow Ch. 1 (ul/min)", "Flow Ch. 2 (ul/min)", "Flow Ch. 3 (ul/min)", "Flow Ch. 4 (ul/min)", "measuring time (seconds)", 
            ]
    with open(savePath,"w") as f:
        # First write headers:
        f.write("".join([i+"," for i in columns]) + "\n")
        # and start the measurement
        p = [False,False,False,False]
        s = [False,False,False,False]
        data = list()
        breakTime = 1/acquisitionRate
        measurementStart = time.time()
        measurementEnd = measurementStart + measureTime
        while True:
            startTime = time.time()
            if startTime > measurementEnd:
                break
            for i in range(4):
                try:
                    p[i] =pelveflow.getPressure(i + 1)
                except ConnectionError:
                    # Log it as a NaN, warn the user, and continnue as to not lose data
                    warnings.warn(f"Pressure in channel {i+1} could not be read at least once.")
                    p[i] = np.nan
            for i in range(4):
                try:
                    s[i] =pelveflow.getSensorData(i + 1)
                except ConnectionError:
                    # Log it as a NaN, warn the user, and continnue as to not lose data
                    warnings.warn(f"Flowrate in channel {i+1} could not be read at least once.")
                    s[i] = np.nan
            endTime = time.time()
            delta = endTime - startTime
            middleTime = startTime + (delta / 2)
            timeSinceStart = middleTime - measurementStart
            data = [middleTime,timeSinceStart,*p,*s,delta]
            f.write( "".join([str(i)+"," for i in data]) + "\n" )
            # data.append([middleTime,timeSinceStart,*p,*s,delta])
            if startTime-time.time() < breakTime:
                time.sleep(breakTime)
            else:
                warnings.warn(f"Requested acquisition rate ({acquisitionRate} Hz) could not be reached, working at max possible rate instead (approx. {1 / delta} Hz)")
    print(f"Measurement complete, data is saved to {savePath}.")
