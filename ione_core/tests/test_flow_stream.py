from unittest import TestCase

from ione_core.flow_stream import _consume_stream_with_heartbeat


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


def _chunk(id="", name="", arguments="", finish_reason=None):
	function = AttrObject(name=name, arguments=arguments)
	tool_call = AttrObject(index=0, id=id, function=function)
	delta = AttrObject(content=None, tool_calls=[tool_call])
	choice = AttrObject(delta=delta, finish_reason=finish_reason)
	return AttrObject(choices=[choice], usage=None)
