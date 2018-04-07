from random import randint
from threading import Lock
from _thread import start_new_thread
from os.path import exists
from asyncio import sleep
from ctypes import cdll

from utils import is_wallaby

from highway import log as logging



ANALOG = 1
DIGITAL = 2
NAMED_MODES = {ANALOG : "analog", DIGITAL : "digital"}
REVERSE_NAMED_MODES = {v : k for k, v in NAMED_MODES.items()}
MODES = tuple(NAMED_MODES.keys())

CONFIG_PATH = "fl0w.cfg"
IS_WALLABY = is_wallaby()
LIB_WALLABY = "/usr/lib/libwallaby.so"

READOUT_TEMPLATE = {
	ANALOG : [],
	DIGITAL : []
}

def valid_port(port, mode):
	if mode == ANALOG:
		return port >= 0 and port <= 5
	elif mode == DIGITAL:
		return port >= 0 and port <= 9
	return False

class SensorReadout:
	def __init__(self, poll_rate=0.2):
		self.poll_rate = poll_rate
		
		self.handler_lock = Lock()
		self.handlers = {}

		self.running = True
		
		self.readout_required = READOUT_TEMPLATE.copy()
		
		# Wallaby library avaliable?
		if not exists(LIB_WALLABY):
			logging.warning("Wallaby library unavaliable.")
			self.get_sensor_value = self.__get_random_value
		else:
			self.wallaby_library = cdll.LoadLibrary(LIB_WALLABY)
			self.get_sensor_value = self.__get_sensor_value
			

	async def run(self):
		while self.running:
			current_values = {
				ANALOG : {},
				DIGITAL : {}
			}

			for mode in MODES:
				for port in self.readout_required[mode]:
					current_values[mode][port] = self.get_sensor_value(port, mode)
			
			self.handler_lock.acquire()
			for handler in self.handlers:
				readouts = 0
				
				response = {ANALOG : {}, DIGITAL : {}}

				for mode in MODES:
					for port in self.handlers[handler][mode]:
						response[mode][port] = current_values[mode][port]
						readouts += 1
				if readouts != 0:
					await handler.send(response, "sensor_stream")
			self.handler_lock.release()
			
			await sleep(self.poll_rate)


	def stop(self):
		self.running = False


	def subscribe(self, port, mode, handler):
		if port not in self.readout_required[mode]:
			self.readout_required[mode].append(port)
		if not handler in self.handlers:
			self.handler_lock.acquire()
			self.handlers[handler] = READOUT_TEMPLATE.copy()
			self.handler_lock.release()
		
		self.handler_lock.acquire()
		self.handlers[handler][mode].append(port)
		self.handler_lock.release()


	def unsubscribe(self, port, mode, handler):
		if handler in self.handlers:
			if port in self.handlers[handler][mode]:
				self.handler_lock.acquire()
				
				del self.handlers[handler][mode][ \
					self.handlers[handler][mode].index(port)]
				
				self.handler_lock.release()
				self.determine_required_readouts()


	def determine_required_readouts(self):
		readout_required = READOUT_TEMPLATE.copy()

		self.handler_lock.acquire()
		for handler in self.handlers:
			for mode in MODES:
				for port in self.handlers[handler][mode]:
					if not port in readout_required[mode]:
						readout_required[mode].append(port)
		self.handler_lock.release()
		self.readout_required = readout_required


	async def unsubscribe_all(self, handler):
		successful = False
		if handler in self.handlers:
			self.handler_lock.acquire()
			del self.handlers[handler]
			self.handler_lock.release()
			successful = True
			self.determine_required_readouts()
		await handler.send(successful, "sensor_unsubscribe")


	def handler_disconnected(self, handler):
		if handler in self.handlers:
			self.handler_lock.acquire()
			del self.handlers[handler]
			self.handler_lock.release()
			self.determine_required_readouts()


	def __get_sensor_value(self, port, mode):
		if mode == SensorReadout.ANALOG:
			return self.wallaby_library.analog(port)
		elif mode == SensorReadout.DIGITAL:
			return self.wallaby_library.digital(port)


	def __get_random_value(self, port, mode):
		if mode == ANALOG:
			return randint(0, 4095)
		elif mode == DIGITAL:
			return randint(0, 1)


