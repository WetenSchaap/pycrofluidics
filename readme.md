# pycrofluidics

This Python module can be used to control [Elveflow](https://www.elveflow.com/) microfluidic devices. Elveflow provides a solid Python API, these are just convenient, simpler bindings that hide (some of) the complexities of the direct bindings.

## Capabilities

This module can currently access all functions of the following devices:

- The [OB1 pressure controller](https://www.elveflow.com/microfluidic-products/microfluidics-flow-control-systems/ob1-pressure-controller/). Tested on Mk4, but should work for older versions as well
- The [MUX distribution](https://www.elveflow.com/microfluidic-products/microfluidics-flow-control-systems/mux-distrib/). This code may also work on other MUX-devices, but it is not guaranteed!

Our lab has no other Elveflow devices, but contributions are welcome.

## Usage

The usage is (hopefully) pretty straightforward. I provide a very short example for using this interactively below, for more details, look at the individual files.

### OB1 pressure controller

The OB1 is a [pressure controller](https://www.elveflow.com/microfluidic-products/microfluidics-flow-control-systems/ob1-pressure-controller/). We have an OB1-Mk4 in our lab, so this is all tested on that. However, it *should* work on earlier versions too. Open an issue if not.

``` python
import pycrofluidics as pf
ob1 = pf.Pelve() 
ob1.open() # device is now connected. You can also use a 'with' statement ("with pf.Pelve() as ob1:")
ob1.loadCallibration() # Load pressure callibration (you can perform pressure callibration using ob1.performCallibration(), follow the regular procedure for callibrationg the pressure channels)
ob1.setPressure(channel = 1, pressure = 10) # sets pressure in channel 1 to 10 mbar
ob1.getPressure(1) # gets current pressure in channel 1
# now lets add a digital flow sensor:
ob1.addSensor(channel=1,sensorType=4,resolution=7,sensorDig=1,sensorIPACalib=0)
# inputted values are: Channel at which sample is connected, the type of sensor (print options with pf.printSensorTypes()), the resolution of sensor (see pf.printSensorResolutions(), whether you are using a digital sensor, whether the sensor should use the IPA callibration.
ob1.getSensorData(1) # get sensor data from channel 1 (obviously will not work if no sensor was added)

# If you want to control the flow by flowrate (instead of pressure) we need a PID feedback control:
ob1.startRemote() # This will start "remote operation mode", a control loop in the background which automatically reads all sensors and regulators. No direct call to the OB1 can be made until the stopRemote function is called. Until then only function accessing this loop (remoteGetData, remoteSetTarget) are allowed.
ob1.getPressure(1) # this will no longer work and error!
pressure, flow = ob1.remoteGetData(1) # get pressure and flowrate from channel 1
ob1.remoteAddPID( channelP = 2, channelS = 1, P = 0.01, I = 0.01) # setup a PID feedback loop with P and I set, using pressure channel 2 and the flow rate sensor on channel 1. The PID will immediately activate after running
ob1.remoteSetTarget(channel = 2, target = 100) # tell PID to work towards a 100µl/min flow in channel 2
ob1.remotePausePID(channel = 2) # pause the PID
ob1.stopRemote() # stop the PID stuff, return to normal, pressure-controlled status.
ob1.close() # always close ob1 before leaving, or you may not be able to reconnect without restarting/unplugging device. Use 'with' statement if possible.
```

### MUX distributor

The [MUX distribution](https://www.elveflow.com/microfluidic-products/microfluidics-flow-control-systems/mux-distrib/) lets you switch between channels. My code may also work on other MUX-devices, but it is not guaranteed!

``` python
import pycrofluidics as pf
mux = pf.MUXelve() 
mux.open( home = True ) # device is now connected, and will home automatically. You can also use a 'with' statement (with pf.MUXelve() as mux: etc)
mux.set_valve(2, blocking = True) # move to valve nr 2. Stops python code until it has arrived there
mux.get_valve()  # gets current position (hopefully 2)
mux.close() # always close mux before leaving, or you may not be able to reconnect without restarting/unplugging device. Use  'with' statement if possible.
```

### Protocols

The protocols submodule contains some (to me) useful shortcuts, like injecting a certain amount in a microfluidic channel using the OB1 and the MUX ditribution. Look at the python file to see what is available.

## Installation

Please be aware that you *cannot* use this module directly after installation, you will need to manually point to the SDK and DLL that elveflow provides when purchasing one of their devices. I assume your device is set-up otherwise. These steps need to be taken whether you use this module, or use the Elveflow-provided Python SDK directly. I only tested this with Elveflow SDK version 3.07.02, but this should be pretty universal. 

1. Download the Elveflow Microfluidic software and SDK [here](https://www.elveflow.com/microfluidic-products/microfluidics-software/elveflow-software-sdk/).
2. Unzip the contents of the downloaded file and place them where you will not lose them (so probably not your "Downloads" folder).
3. If you did not install the "Elveflow Smart Interface (ESI)" yet, do that now: located at ``ESI_V[version nr]/setup.exe`` in the unzipped file.
4. Install additional required software:
   - 64-bit drivers: ``SDK_V[version nr]/Extra Install For x64 Libraries/setup.exe``
   - FTDI drivers: found in install folder of ESI: ``C:\Program Files(x86)\Elvesys\driver`` (look for ``driver_MUX_distAndBFS.exe``)
5. Now you need to find out the name of the Elveflow devices you are using. Do this using the National Instruments Measurement and Automation Explorer ("NI MAX") software. The NI MAX Software should be automatically installed with Elveflow Smart Interface.
   1. Turn on all of your devices. Don **not** plug in your devices yet. Do **not** start the ESI software to control them.
   2. Open the NI MAX software
   3. Expand the menu with "devices and interfaces" on the left side. You see a list of all devices. There should be things like ``ASRL3::INSTR`` (ignore ``COM3`` immediately after it). Write all devices down
   4. Plug in your Elveflow device and refresh the device and interfaces list (``F5``). The name that sappeared is your device. Do this for all your devices. Keep track of which device has which name.
6. Install this module now, using ``pip install pycrofluidics`` (or using ``poetry``, or something else)
7. Now, you need to tell pycrofluidics where to look for the SDK and dll files you downloaded before, and the name of your devices. You do this by creating and editing a configuration file. To create the file, run from the terminal:

``` bash
pycrofluidics_create_config
```

This will initialize the configuration file and return where it is located. Open this file. The content will be something like:

``` yaml
elveflow_dll : /path/to/the/elveflow/dll
elveflow_sdk : /path/to/the/elveflow/sdk
ob1_name : ASRL3::INSTR
mux_name : ASRL4::INSTR
ob1_callibration : /path/to/a/file/close/to/this/one
```

Set ``elveflow_dll`` to the path to the dll's you've downloaded, presumably something like ``C:\Users\YOURNAME\Code\Elveflow\SDK_V[version nr]\DLL\DLL64``

Set ``elveflow_sdk`` to the path to the Python SDK you've downloaded, presumably something like ``C:\Users\YOURNAME\Code\Elveflow\SDK_V[version nr]\DLL\Python\Python_64``

Replace ``[DEVICE]_name`` with the device names you discovered earlier. If you do not have a device which is in the list (e.g., the mux distributor), just leave it as it is.

Now you are ready to use this module!


## FAQ

> I keep getting error "-8007" (ESI software seems to have connection with Device, close ESI before continuing in Python), but the ESI software is not open. What is going wrong?

Probably, your device name changed. This happens when you plug the device into a different USB port, and sometimes just randomly. Change the name of the device in the config file (you can see its location by running ``pycrofluidics.where_is_the_config_file()``). If this keeps happening, you can also supply the device name directly to the objects, e.g. ``pycrofluidics.Pelve(deviceName="ASRL3::INSTR")`` to override the default. So you don't have to keep changing the default values.

> I have more than one of the same device. Can I still use this code

Yes. You should supply the correct device name when creating the connection (e.g. ``pycrofluidics.Pelve(deviceName="ASRL3::INSTR")``) instead of relying on the config file. It should *just work*™ that way.
