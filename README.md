# USB2fac ⚡️

This project provides a verification of connected USB devices, by using the [Duo Auth API](https://duo.com/docs/authapi).

When a device is connected for the first time to the host, an action will be triggered based on the configuration and it will require to be confirmed with a Duo push request.
If the device is not confirmed, or explicitly rejected, a second action (also configurable) will be triggered.
The purpose of **USB2fac** is to orchestrate the described actions, while keeping track of all the connected USB devices. In the event of an incident, this information can be useful for the Security team.

## Installation

For now, only OSX is supported.

USB2fac requires [libusb](http://libusb.info/), you can install it using brew:

```
$ brew install libusb
```

Then you need to install the python bindings, [pyusb](https://walac.github.io/pyusb/):

```
$ sudo pip install pyusb --pre
```

Finally you will need the python library [requests](http://docs.python-requests.org/). Install it using pip:

```
$ pip install requests
```

Also, you will need the [Duo Auth API](https://duo.com/docs/authapi) and create an application, in order to use the 2-factor capabilities.

Provide your integration key, secret key and API hostname in the [configuration file](https://github.com/uber/usb2fac/blob/master/config.ini.example).

## Usage

```
Usage: USB2fac.py [-h|--help] [ARGUMENT [PARAMETER]] [ARGUMENT [PARAMETER]] ..

Arguments:
  -h, --help          Shows this help message and exit.
  -D, --find          Discover devices connected and stores them as seen.
  -R, --reset         Reset all the rejected devices.
  -l, --log    FILE   Log file for 2facUSB. Default is USB2fac.log
  -C, --conn   VALUE  Paranoia level for the connect action triggered: 1 = log, 2 = lock, 3 = shutdown
  -R, --action VALUE  Paranoia level for the reject action triggered: 1 = log, 2 = lock, 3 = shutdown
  -c, --config FILE   File with Duo API access and configuration. Overrides all parameters. Default is None
  -o, --file   FILE   JSON file to be used as storage for seen devices. Default is USB2fac.json
  -b, --backup FILE   JSON file with a backup of the trusted/seen USB devices. Default is USB2fac.bak
  -r, --reject FILE   JSON file to keep track of the rejected USB devices. Default is rejected.json
  -p, --pid    FILE   File to keep track of the daemon PID. Default is USB2fac.pid
  -u  --user   VALUE  Username to use for the DUO integration and send the push request.

Examples:
  USB2fac.py -D -o usb.json -b usb.bak
  USB2fac.py -L 0 -o usb.json -b usb.bak -r reject.json
```

## Contributing

We :heart: contributions. Found a bug or looking for a new feature? Open an issue and we'll respond as fast as we can. Or, better yet, implement it yourself and open a pull request! We ask that you include tests to show the bug was fixed or the feature works as expected.

**Note:** All contributors also need to fill out the [Uber Contributor License Agreement](http://t.uber.com/cla) before we can merge in any of your changes.


## License

MIT License, please see [LICENSE](https://github.com/uber/usb2fac/blob/master/LICENSE) for details.
