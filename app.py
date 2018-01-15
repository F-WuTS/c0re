from os.path import isfile, isdir
from threading import Lock
from re import compile as re_compile
from subprocess import check_output, CalledProcessError, Popen, PIPE, STDOUT
from _thread import start_new_thread
from time import sleep
from asyncio import get_event_loop, ensure_future

# bottle (web-server)
from bottle import route, static_file
from bottle import run as run_bottle

# highway
from highway import Server
from highway import Handler as Handler_

# highway utilities
from highway import log as logging
from highway import ConnectionClosed

from meh import Config, Option, ExceptionInConfigError

from sensor_readout import SensorReadout
from sensor_readout import REVERSE_NAMED_MODES
from sensor_readout import valid_port as valid_sensor_port

from utils import play_sound, PlaybackFailure, valid_port

CONFIG_PATH = "fl0w.cfg"

INDEX_PATH = "dashb0ard"
STATIC_PATH = INDEX_PATH + "/static"

config = Config()
config += Option("address", "127.0.0.1")
config += Option("ws_port", 3077, validator=valid_port)
config += Option("http_port", 8080, validator=valid_port)
config += Option("highway_debug", False)
config += Option("bottle_debug", False)
config += Option("fl0w_debug", False)
config += Option("identify_sound", "resources/identify.wav", validator=isfile)
config += Option("output_unbufferer", "stdbuf -o 0")

try:
    config = config.load(CONFIG_PATH)
except (IOError, ExceptionInConfigError):
    config.dump(CONFIG_PATH)
    config = config.load(CONFIG_PATH)


class Handler(Handler_):
	def on_close(self, code, reason):
		logging.info("Unsubscribing '%s:%i' from sensor readouts." % (*self.remote_address, ))
		sensor_readout.handler_disconnected(self)


server = Server(Handler, debug=config.highway_debug)
sensor_readout = SensorReadout()


loop = get_event_loop()
ensure_future(sensor_readout.run())

"""
{"analog" : {1, 2, 3}, "digital" : {1, 2, 3}}
"""
async def process_sensor_request(data, handler, route, action):
	successful = True
	for mode in REVERSE_NAMED_MODES:
		if mode in data:					
			for port in data[mode]:
				if type(port) is int:
					if valid_sensor_port(port, 
						REVERSE_NAMED_MODES[mode]):
						
						action(port, REVERSE_NAMED_MODES[mode], 
							handler)
					else:
						successful = False
						break
				else:
					successful = False
					break
	await handler.send(successful, route)


@server.route("identify")
async def identify(data, handler):
	successful = False
	try:
		play_sound(config.identify_sound)
		successful = True
	except PlaybackFailure:
		pass
	await handler.send(successful, "identify")


@server.route("sensor_poll_rate")
async def sensor_poll_rate(data, handler):
	successful = False
	if type(data) in (int, float) and data >= 0.1:
		sensor_readout.poll_rate = data
		successful = True
	await handler.send(successful, "sensor_poll_rate")


@server.route("sensor_unsubscribe_all")
async def sensor_unsubscribe_all(data, handler):
	sensor_readout.unsubscribe_all(handler)



@server.route("sensor_subscribe")
async def sensor_subscribe(data, handler):
	await process_sensor_request(data, handler, "sensor_subscribe", 
		sensor_readout.subscribe)


@server.route("sensor_unsubscribe")
async def sensor_unsubscribe(data, handler):
	await process_sensor_request(data, handler, "sensor_unsubscribe", 
			sensor_readout.unsubscribe)


@server.route("shutdown")
async def shutdown(data, handler):
	successful = False
	try:
		check_output(["shutdown", "now"])
		successful = True
	except CalledProcessError:
		pass
	await handler.send(successful, "shutdown")


@server.route("reboot")
async def reboot(data, handler):
	successful = False
	try:
		check_output(["reboot"])
		successful = True
	except CalledProcessError:
		pass
	await handler.send(successful, "reboot")


@server.route("upgrade")
async def upgrade(data, handler):
	await stream_program_output("apt-get update && apt-get upgrade", 
		"upgrade", handler)


@server.route("kill_botball")
async def kill_botball(data, handler):
	await stream_program_output("killall botball_user_program", 
		"kill_botball", handler)


@server.route("reset_coproc")
async def reset_coproc(data, handler):
	await stream_program_output("wallaby_reset_coproc", 
		"reset_coproc", handler)


@server.route("reset_coproc")
async def restart_x11(data, handler):
	await stream_program_output("systemctl restart x11", 
		"restart_x11", handler)


@server.route("restart_harrogate")
async def restart_harrogate(data, handler):
	await stream_program_output("systemctl restart harrogate", 
		"restart_harrogate", handler)


@server.route("restart_networking")
async def restart_networking(data, handler):
	await stream_program_output("systemctl restart networking", 
		"restart_networking", handler)


async def stream_program_output(command, route, handler):
	await handler.send("> %s\n" % command, route + "_output")
	command = "%s %s" % (config.output_unbufferer, command)
	program = Popen(command, stdout=PIPE, stderr=STDOUT, shell=True)
	
	# Stream output async
	loop = get_event_loop()
	ensure_future(_stream_program_output(program, route, handler))


async def _stream_program_output(program, route, handler):			
	has_disconnected = False
	# Poll process for new output until finished
	for line in iter(program.stdout.readline, b""):
		line = line.decode()
		try:
			await handler.send(line, route + "_output")
		except ConnectionClosed:
			has_disconnected = True
			logging.warning(line.rstrip("\n"))
	program.wait()
	if not has_disconnected:
		exit_code = program.returncode if type(program.returncode) is int else -1
		await handler.send(exit_code, route + "_exit")



@route("/")
def index():
	return static_file("index.html", root="dashb0ard")

@route("/static/<filepath:path>")
def static(filepath):
	return static_file(filepath, root="dashb0ard/static")


if isdir(STATIC_PATH) and isdir(INDEX_PATH):
	start_new_thread(run_bottle, (), {"host" : config.address,
		"port" : config.http_port, "quiet" : not config.bottle_debug})

	logging.header("Serving dashb0ard on 'http://%s:%s'" % (config.address, 
	config.http_port))

else:
	logging.error("dashb0ard not found.")


try:
	logging.header("Starting fl0w on 'ws://%s:%s'" % (config.address, 
		config.ws_port))
	server.start(config.address, config.ws_port)
except KeyboardInterrupt:
	# server.stop()
	pass