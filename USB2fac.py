#!/usr/bin/env python
#
# Copyright (c) 2016 Uber Technologies, Inc.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# Script to enable 2fac confirmation to newly connected USB devices.
#
# Make sure libusb, pyUSB and requests are installed in the system:
#
#  brew install libusb
#  sudo pip install pyusb --pre
#  sudo pip install requests

import os
import re
import sys
import json
import hmac
import email
import base64
import getopt
import signal
import urllib
import hashlib
import logging
import platform
import requests
import usb.core
import usb.util
import subprocess
import ConfigParser
from time import sleep
import logging.handlers

LOG_LEVEL = logging.INFO
logger = logging.getLogger(__name__)
logger.setLevel(LOG_LEVEL)

class USBLogger(object):
	def __init__(self, logger, level):
		self.logger = logger
		self.level = level
	def write(self, message):
		if message.rstrip() != "":
			self.logger.log(self.level, message.rstrip())

# List to hold those devices that were requested, to avoid smashing Duo
requested_ids = []
# List to hold the trusted devices that get connected
current_trusted_ids = []

# Iterations to clear requested_ids
# This will be multiplied by the LOOP_DELAY
clear_requested_timeout = 300
clear_requested_current = 0

# Configuration with default values
CONFIGURATION = {
	'LOG_FILE': 'USB2fac.log',
	'DEVICES_FILE': 'USB2fac.json',
	'BACKUP_FILE': 'USB2fac.bak',
	'REJECTED_FILE': 'rejected.json',
	'CONFIG_FILE': None,
	'PID_FILE': 'USB2fac.pid',
	'PARANOIA_CONNECT': 1,
	'PARANOIA_REJECT': 2,
	'DISCOVER': False,
	'RESET': False,
	'LOOP_DELAY': 0.2,
	'USERNAME': '',
	'DUO_IKEY': '',
	'DUO_SKEY': '',
	'DUO_HOST': ''
}

# Function that creates a notification in OSX
def osx_notification(title, message):
	subprocess.call(
		'osascript -e \'display notification "%s" with title "%s"\''
		% (message, title),
	shell=True)

# Function to retrieve a configuration value
def get_conf(confKey):
	try:
		data = CONFIGURATION[confKey]
	except:
		data = None
	return data

# Function to set a configuration value with the provided data
def set_conf(confKey, confValue):
	global CONFIGURATION
	CONFIGURATION[confKey] = confValue

# Function to load configuration from file
def load_conf(FILE):
	try:
		Config = ConfigParser.ConfigParser()
		Config.read(get_conf('CONFIG_FILE'))
		# Duo Auth API
		set_conf(
			'DUO_IKEY',
			Config.get('DuoApiAuth', 'ikey')
		)
		set_conf(
			'DUO_SKEY',
			Config.get('DuoApiAuth', 'skey')
		)
		set_conf(
			'DUO_HOST',
			Config.get('DuoApiAuth', 'host')
		)
		set_conf(
			'USERNAME',
			Config.get('DuoApiAuth', 'username')
		)
		# Configuration parameters
		set_conf(
			'PARANOIA_CONNECT',
			int(Config.get('Configuration', 'paranoia_connect'))
		)
		set_conf(
			'PARANOIA_REJECT',
			int(Config.get('Configuration', 'paranoia_reject'))
		)
		set_conf(
			'LOOP_DELAY',
			float(Config.get('Configuration', 'loop_delay'))
		)
		set_conf(
			'DEVICES_FILE',
			Config.get('Configuration', 'devices_file')
		)
		set_conf(
			'BACKUP_FILE',
			Config.get('Configuration', 'backup_file')
		)
		set_conf(
			'REJECTED_FILE',
			Config.get('Configuration', 'rejected_file')
		)
		set_conf(
			'LOG_FILE', Config.get('Configuration', 'log_file')
		)
		set_conf(
			'CONFIG_FILE',
			Config.get('Configuration', 'config_file')
		)
		set_conf(
			'PID_FILE',
			Config.get('Configuration', 'pid_file')
		)
		#set_conf('DISCOVERY', Config.get('Configuration', 'discovery'))
		#set_conf('RESET', Config.get('Configuration', 'reset'))

		logger.info('Configuration succesfully parsed')
	except:
		e = sys.exc_info()[0]
		logger.error('Error parsing configuration: ' + str(e))
		logger.info('Using default parameters without DUO push')

# Function to display usage of script
def usage():
	print
	print 'Script to enable 2fac confirmation to newly connected USB devices'
	print
	print 'Usage: %s [-h|--help] [ARGUMENT [PARAMETER]] [ARGUMENT [PARAMETER]] ..' % (sys.argv[0])
	print
	print 'Arguments:'
	print '  -h, --help           Shows this help message and exit.'
	print '  -D, --find           Discover devices connected and stores them as seen.'
	print '  -R, --reset          Reset all the rejected devices.'
	print '  -l, --log    FILE    Log file for 2facUSB. Default is %s' % (get_conf('LOG_FILE'))
	print '  -C, --conn   VALUE   Paranoia level for the connect action triggered: 1 = log, 2 = lock, 3 = shutdown'
	print '  -P, --action VALUE   Paranoia level for the reject action triggered: 1 = log, 2 = lock, 3 = shutdown'
	print '  -c, --config FILE    File with Duo API access and configuration. Overrides all parameters. Default is %s' % (get_conf('CONFIG_FILE'))
	print '  -o, --file   FILE    JSON file to be used as storage for seen devices. Default is %s' % (get_conf('DEVICES_FILE'))
	print '  -b, --backup FILE    JSON file with a backup of the trusted/seen USB devices. Default is %s' % (get_conf('BACKUP_FILE'))
	print '  -r, --reject FILE    JSON file to keep track of the rejected USB devices. Default is %s' % (get_conf('REJECTED_FILE'))
	print '  -p, --pid    FILE    File to keep track of the daemon PID. Default is %s' % (get_conf('PID_FILE'))
	print '  -u  --user   VALUE   Username to use for the DUO integration and send the push request.'
	print
	print 'Examples:'
	print '  %s -D -o usb.json -b usb.bak' % (sys.argv[0])
	print '  %s -C 2 -P 1 -o usb.json -b usb.bak -r reject.json' % (sys.argv[0])

# Function to sign a request to be sent to Duo. Output is Date and Auth headers.
def get_duo_headers(method, host, path, params, skey, ikey):
    now = email.Utils.formatdate()
    canon = [now, method.upper(), host.lower(), path]
    args = []
    for key in sorted(params.keys()):
        val = params[key]
        if isinstance(val, unicode):
            val = val.encode("utf-8")
        args.append(
            '%s=%s' % (urllib.quote(key, '~'), urllib.quote(val, '~')))
    canon.append('&'.join(args))
    canon = '\n'.join(canon)
    sig = hmac.new(skey, canon, hashlib.sha1)
    auth = '%s:%s' % (ikey, sig.hexdigest())

    return {'Date': now, 'Authorization': 'Basic %s' % base64.b64encode(auth)}

# Function to parse the DUO Auth API configuration
def duo_2fac_confirmation(description):
	# Extract username for DUO from chef configuration
	username = get_conf('USERNAME')
	duo_host = get_conf('DUO_HOST')
	duo_skey = get_conf('DUO_SKEY')
	duo_ikey = get_conf('DUO_IKEY')

	# Do we have valid DUO integration access?
	if not duo_host and not duo_ikey and not duo_skey:
		logger.error('DUO Auth API configuration not found')
		return False

	# Verify duo is good
	duo_path = '/auth/v2/ping'
	duo_url = 'https://' + duo_host + duo_path
	r = requests.get(duo_url)
	if r.json()['stat'] != 'OK':
		return False

	# Verify creds for duo
	duo_path = '/auth/v2/check'
	duo_url = 'https://' + duo_host + duo_path
	duo_headers = get_duo_headers(
		'GET',
		duo_host,
		duo_path,
		{},
		duo_skey,
		duo_ikey
	)
	r = requests.get(duo_url, headers=duo_headers)
	if r.json()['stat'] != 'OK':
		return False

	# Make sure this usename is ready for push
	duo_path = '/auth/v2/preauth'
	duo_url = 'https://' + duo_host + duo_path
	params = {'username': username}
	duo_headers = get_duo_headers(
		'POST',
		duo_host,
		duo_path,
		params,
		duo_skey,
		duo_ikey
	)
	r = requests.post(duo_url, data=params, headers=duo_headers)
	if r.json()['stat'] != 'OK':
		return False

	# Submit duo push request
	duo_path = '/auth/v2/auth'
	duo_url = 'https://' + duo_host + duo_path
	push_msg = 'USB Connect: ' + description
	params = {
		'username': username,
		'factor': 'push',
		'device': 'auto',
		'type': push_msg
	}
	duo_headers = get_duo_headers(
		'POST',
		duo_host,
		duo_path,
		params,
		duo_skey,
		duo_ikey
	)
	r = requests.post(duo_url, data=params, headers=duo_headers)
	if r.json()['response']['result'] == 'allow':
		return True
	else:
		return False

# Function generic function to store a JSON file
def save_devices_file(jsonData, FILE):
	with open(FILE, 'w+') as f:
		json.dump(jsonData, f, sort_keys=False, indent=2, separators=(',', ': '))

# Function to backup a structure of trusted devices
def backup_trusted_devices(jsonData):
	save_devices_file(jsonData, get_conf('BACKUP_FILE'))

# Function to keep track of rejected devices
def save_rejected_devices(jsonData):
	save_devices_file(jsonData, get_conf('REJECTED_FILE'))

# Function to persist the JSON with seen USB devices
def save_trusted_devices(jsonData):
	save_devices_file(jsonData, get_conf('DEVICES_FILE'))

# Function that loads the rejected devices
def load_trusted_devices():
	return load_devices(get_conf('DEVICES_FILE'))

# Function that loads the trusted devices
def load_rejected_devices():
	return load_devices(get_conf('REJECTED_FILE'))

# Function that loads the JSON file with seen USB devices
def load_devices(FILE):
	try:
		with open(FILE, 'r+') as f:
			data = json.load(f)
	except:
		data = []

	return data

# Function to generate a device_id
def gen_device_id(vendor, product):
	return hashlib.md5(str(vendor) + str(product)).hexdigest()

# Function to generate a list of device ids
def gen_device_id_list(devices):
	devices_ids = []
	for d in devices:
		devices_ids.append(d.keys()[0])

	return devices_ids

# Helper function to create an object for a device
def device_entry(vendor, product, serial, description, device_id):
	data = {
		"vendorId" : vendor,
		"productId" : product,
		"serialNumber" : serial,
		"description" : description
	}
	device_data = {
		device_id : data
	}

	return device_data

# Function that locks the computer
def lock_computer():
	subprocess.call(
		'/System/Library/CoreServices/"Menu Extras"/User.menu/Contents/Resources/CGSession -suspend',
		shell=True
	)

# Function that shutsdown the computer
def shutdown_computer():
	subprocess.call('shutdown -r now', shell=True)

# Function that is triggered when a device is rejected.
# Based on the paranoia level on reject.
def reject_action():
	if get_conf('PARANOIA_REJECT') == 1:
		logger.info('2facUSB Action: Unknown device was rejected')
	elif get_conf('PARANOIA_REJECT') == 2:
		logger.info('2facUSB Action: Locking computer')
		lock_computer()
	elif get_conf('PARANOIA_REJECT') == 3:
		logger.info('2facUSB Action: Shuting down computer')
		shutdown_computer()

# Function that is triggered when a new device is connected.
# Based on the paranoia level on connect.
def connect_action():
	if get_conf('PARANOIA_CONNECT') == 1:
		logger.info('2facUSB Action: Unknown device was connected')
	elif get_conf('PARANOIA_CONNECT') == 2:
		logger.info('2facUSB Action: Locking computer')
		lock_computer()
	elif get_conf('PARANOIA_CONNECT') == 3:
		logger.info('2facUSB Action: Shuting down computer')
		shutdown_computer()

# Function to reset all rejected devices
def reset_rejected():
	save_rejected_devices([])

# Function to do input validation on device supplied ids
def sanitize_id(id):
	return re.sub(r'[^-_A-Za-z0-9\ \']', '', id)

# Function to discover currently connected devices.
# Parameter is to verify them against trusted or just return them.
def discover_devices(check_trusted=False):
	dev = usb.core.find(find_all=True)

	current_data = []
	for cfg in dev:
		vendor = hex(cfg.idVendor)
		product = hex(cfg.idProduct)
		# Serial number
		try:
			serial = sanitize_id(str(usb.util.get_string(cfg, cfg.iSerialNumber)))
		except:
			serial = 'Unknown'
		# Description
		try:
			description = sanitize_id(str(usb.util.get_string(cfg, cfg.iProduct)))
		except:
			description = 'Unknown'

		device_id = gen_device_id(vendor, product)
		data = {
			"vendorId" : vendor,
			"productId" : product,
			"serialNumber" : serial,
			"description" : description
		}
		current_data.append(
			device_entry(vendor, product, serial, description, device_id)
		)

		if check_trusted:
			rejected = load_rejected_devices()
			rejected_ids = gen_device_id_list(rejected)
			trusted = load_trusted_devices()
			trusted_ids = gen_device_id_list(trusted)

			global requested_ids
			if device_id not in trusted_ids and device_id not in requested_ids:
				if device_id in rejected_ids:
					logger.info(
						'REJECTED DEVICE CONNECTED! %s'
						% (device_entry(vendor, product, serial, description, device_id))
					)
					osx_notification(
						'Rejected USB Device Connected',
						'Use DUO in your phone to verify and trust this device'
					)
				else:
					logger.info(
						'UNKNOWN DEVICE CONNECTED! %s'
						% (device_entry(vendor, product, serial, description, device_id))
					)
					osx_notification(
						'Unknown USB Device Connected',
						'Use DUO in your phone to verify and trust this device'
					)

				# Based on the level of paranoia, do the connect action
				connect_action()

				# Do 2fac verification
				logger.info('Verifying device...')
				if duo_2fac_confirmation(description):
					# Backup trusted devices
					backup_trusted_devices(trusted)
					# Save device as trusted
					trusted.append(
						device_entry(vendor, product, serial, description, device_id)
					)
					save_trusted_devices(trusted)
					logger.info('Verified and saved')
					osx_notification('USB Device Trusted', 'Have a nice day!')
				else:
					# No confirmation through 2fac, do the needful
					rejected.append(
						device_entry(vendor, product, serial, description, device_id)
					)
					save_rejected_devices(rejected)
					logger.info('Device has been Rejected')
					reject_action()

				# Avoid smashing DUO with requests
				requested_ids.append(device_id)

			# Log trusted device
			if device_id not in current_trusted_ids:
				logger.info(
					'Trusted device connected: %s'
					% (device_entry(vendor, product, serial, description, device_id))
				)
				current_trusted_ids.append(device_id)

			# Avoid smashing DUO with requests
			if (
				clear_requested_current > clear_requested_timeout and
				device_id in requested_ids
			):
				requested_ids.remove(device_id)

	return current_data

# Function that handles SIGUSR1 and SIGUSR2 for 2facUSB
def signal_handler(sig, frame):
	if sig == signal.SIGHUP:
		# SIGHUP reloads configuration
		if get_conf('CONFIG_FILE') is not None:
			logger.info('Received SIGHUP: Reloading configuration')
			load_conf(get_conf('CONFIG_FILE'))
	if sig == signal.SIGUSR1:
		# SIGUSR1 rediscovers currect devices
		logger.info('Received SIGUSR1: Discovering connected devices')
		discovery()
	if sig == signal.SIGUSR2:
		# SIGUSR1 reloads configuration
		logger.info('Received SIGUSR2: Reseting rejected devices')
		reset_rejected()

# Function that creates a pid file
def create_pidfile():
	PID_FILE = get_conf('PID_FILE')
	pid = str(os.getpid())
	with open(PID_FILE, "w+") as f:
		f.write(pid + "\n")

# Function that detects all current USB devices and persists them in a JSON file
def discovery():
	logger.info('Discovering devices...')
	discovered_devices = discover_devices()
	save_trusted_devices(discovered_devices)

# Function that acts as daemon
def running_daemon():
	# Output to log
	sys.stdout = USBLogger(logger, logging.INFO)
	sys.stderr = USBLogger(logger, logging.ERROR)

	logger.info('Starting 2facUSB...')
	logger.info('PID is %d' % (os.getpid()))

	# Kick off process
	while True:
		try:
			discover_devices(True)
			# Delay a bit
			sleep(get_conf('LOOP_DELAY'))
			global clear_requested_current
			if (clear_requested_current > clear_requested_timeout):
				clear_requested_current = 0
			else:
				clear_requested_current += 1

		except KeyboardInterrupt:
			logger.info('Stopped by CTRL + C')
			sys.exit()

# Main function with parameters extraction and run
def main():
	# Script only works in OSX
	if platform.system() != 'Darwin':
		print 'Sorry, only OSX systems are supported.'
		sys.exit(1)

	# Create pid file
	create_pidfile()

	# Listen for SIGHUP, SIGUSR1 and SIGUSR2
	signal.signal(signal.SIGHUP, signal_handler)
	signal.signal(signal.SIGUSR1, signal_handler)
	signal.signal(signal.SIGUSR2, signal_handler)

	# Setting up logging
	handler = logging.handlers.TimedRotatingFileHandler(
		get_conf('LOG_FILE'),
		when="midnight",
		backupCount=3
	)
	handler.suffix = "%Y-%m-%d.old"
	formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
	handler.setFormatter(formatter)
	logger.addHandler(handler)

	try:
		opts, args = getopt.getopt(
			sys.argv[1:],
			"hDRc:l:C:P:o:b:r:p:u:",
			[
				"help", "find", "reset", "config", "log", "conn",
				"action", "file", "backup", "reject", "pid", "user"
			]
		)
  	except getopt.GetoptError:
  		usage()
  		sys.exit(2)

	for opt, arg in opts:
		if opt in ("-h", "--help"):
			usage()
  			sys.exit()
  		elif opt in ("-D", "--find"):
  			set_conf('DISCOVERY', True)
  		elif opt in ("-R", "--reset"):
  			set_conf('RESET', True)
  		elif opt in ("-c", "--config"):
  			set_conf('CONFIG_FILE', arg)
  			load_conf(get_conf('CONFIG_FILE'))
  			break
  		elif opt in ("-l", "--log"):
  			set_conf('LOG_FILE', arg)
  		elif opt in ("-C", "--conn"):
  			set_conf('PARANOIA_CONNECT', arg)
  		elif opt in ("-P", "--action"):
  			set_conf('PARANOIA_REJECT', arg)
  		elif opt in ("-o", "--file"):
  			set_conf('DEVICES_FILE', arg)
  		elif opt in ("-b", "--backup"):
  			set_conf('BACKUP_FILE', arg)
  		elif opt in ("-r", "--reject"):
  			set_conf('REJECT_FILE', arg)
  		elif opt in ("-p", "--pid"):
  			set_conf('PID_FILE', arg)
  		elif opt in ("-u", "--user"):
  			set_conf('USERNAME', arg)

	if get_conf('DISCOVERY'):
		discovery()
	if get_conf('RESET'):
		reset_rejected()

	# Here we go
	running_daemon()

if __name__ == "__main__":
	main()

# kthxbai
