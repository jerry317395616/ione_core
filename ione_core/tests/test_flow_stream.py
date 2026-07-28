import threading
import time
from unittest import TestCase

from ione_core.flow_stream import _consume_stream_with_heartbeat, keepalive_events


class AttrObject:
	def __init__(self, **values):
		self.__dict__.update(values)


class FakeModelModule:
	class ToolCallBegin:
		def __init__(self, id, name):
			self.id = id
			self.name = name

	class ChatResponse:
		def __init__(self, **values):
			self.__dict__.update(values)

	@staticmethod
	def _attr(obj, key, default=None):
		return getattr(obj, key, default)

	@staticmethod
	def _accumulate_tool_call(acc, delta):
		index = delta.index
		slot = acc.setdefault(index, {"id": "", "name": "", "arguments": ""})
		if delta.id:
			slot["id"] = delta.id
		if delta.function.name:
			slot["name"] = delta.function.name
		if delta.function.arguments:
			slot["arguments"] += delta.function.arguments
		return index

	@staticmethod
	def _finalize_tool_calls(acc):
		return list(acc.values())


class TestFlowStreamHeartbeat(TestCase):
	def test_emits_empty_frames_while_tool_arguments_stream(self):
		chunks = [
			_chunk(id="call-1", name="execute", arguments="{"),
			_chunk(arguments='"code":'),
			_chunk(arguments='"result = 1"}', finish_reason="tool_calls"),
		]

		stream = _consume_stream_with_heartbeat(chunks, model_module=FakeModelModule)
		first = next(stream)
		second = next(stream)
		third = next(stream)
		with self.assertRaises(StopIteration) as stopped:
			next(stream)

		self.assertIsInstance(first, FakeModelModule.ToolCallBegin)
		self.assertEqual([second, third], ["", ""])
		self.assertEqual(stopped.exception.value.finish_reason, "tool_calls")

	def test_keeps_entire_flow_run_alive_between_events(self):
		release = threading.Event()

		def delayed_events():
			release.wait()
			yield "finished"

		stream = keepalive_events(
			delayed_events(),
			interval=0.01,
			heartbeat_factory=lambda: "heartbeat",
		)

		self.assertEqual(next(stream), "heartbeat")
		release.set()
		self.assertEqual(next(stream), "finished")
		with self.assertRaises(StopIteration):
			next(stream)

	def test_finishes_producer_when_browser_closes_stream(self):
		finished = threading.Event()

		def delayed_events():
			time.sleep(0.04)
			finished.set()
			yield "finished"

		stream = keepalive_events(
			delayed_events(),
			interval=0.01,
			heartbeat_factory=lambda: "heartbeat",
		)

		self.assertEqual(next(stream), "heartbeat")
		stream.close()
		self.assertTrue(finished.is_set())


def _chunk(id="", name="", arguments="", finish_reason=None):
	function = AttrObject(name=name, arguments=arguments)
	tool_call = AttrObject(index=0, id=id, function=function)
	delta = AttrObject(content=None, tool_calls=[tool_call])
	choice = AttrObject(delta=delta, finish_reason=finish_reason)
	return AttrObject(choices=[choice], usage=None)
