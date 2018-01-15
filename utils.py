from traceback import print_exception
from sys import exc_info, byteorder
import platform
import os
import struct
import subprocess
import urllib

HIGHEST_PORT = 65535

class HostnameNotChangedError(PermissionError):
	def __init__(self):
		super(PermissionError, self).__init__("hostname could not be changed")

class NotSupportedOnPlatform(OSError):
	def __init__(self):
		super(OSError, self).__init__("feature not avaliable on OS")

class PlaybackFailure(OSError):
	def __init__(self):
		super(OSError, self).__init__("audio playback failed")


def is_wallaby():
	return "3.18.21-custom" in platform.uname().release


def is_linux():
	return platform.uname().system == "Linux"


def is_darwin():
	return platform.uname().system == "Darwin"


def is_windows():
	return platform.uname().system == "Windows"


def set_hostname(hostname):
	if is_linux():
		if os.geteuid() == 0:
			open("/etc/hostname", "w").write(hostname)
		else:
			raise HostnameNotChangedError()
	elif is_darwin():
		if os.geteuid() == 0:
			subprocess.check_call(["scutil", "--set", "HostName", hostname])
		else:
			raise HostnameNotChangedError()
	else:
		raise HostnameNotChangedError()


def get_hostname():
	return platform.uname().node


def get_ip_from_url(url):
	return urllib.parse.urlsplit(url).netloc.split(':')[0]


def play_sound(path):
	if is_linux() or is_darwin():
		try:
			subprocess.check_call(["aplay" if is_linux() else "afplay", path])
		except subprocess.CalledProcessError as e:
			raise PlaybackFailure()
	else:
		raise NotSupportedOnPlatform()


def valid_port(port):
	return type(port) is int and port <= HIGHEST_PORT