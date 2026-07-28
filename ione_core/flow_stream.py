from __future__ import annotations

from typing import Any


def install_flow_stream_heartbeat() -> bool:
	"""Keep Flow SSE connections active while tool-call arguments are streaming."""
	try:
		import flow.lib.model as flow_model
	except ImportError:
		return False

	current = flow_model._consume_stream
	if getattr(current, "_ione_heartbeat", False):
		return False

	_consume_stream_with_heartbeat._ione_heartbeat = True
	flow_model._consume_stream = _consume_stream_with_heartbeat
	return True


def _consume_stream_with_heartbeat(chunks: Any, model_module: Any | None = None):
	if model_module is None:
		import flow.lib.model as model
	else:
		model = model_module

	content_parts: list[str] = []
	tool_calls_acc: dict[int, dict[str, str]] = {}
	announced: set[int] = set()
	usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
	finish_reason: str | None = None

	for chunk in chunks:
		choices = getattr(chunk, "choices", None) or []
		if choices:
			choice = choices[0]
			delta = getattr(choice, "delta", None)
			if delta is not None:
				emitted = False
				text = model._attr(delta, "content")
				if text:
					content_parts.append(text)
					emitted = True
					yield text

				tool_deltas = model._attr(delta, "tool_calls") or []
				for tool_delta in tool_deltas:
					index = model._accumulate_tool_call(tool_calls_acc, tool_delta)
					slot = tool_calls_acc[index]
					if index not in announced and slot["id"] and slot["name"]:
						announced.add(index)
						emitted = True
						yield model.ToolCallBegin(id=slot["id"], name=slot["name"])

				# Flow normally stays silent while arguments stream. An empty text frame keeps
				# Cloudflare and nginx from closing an otherwise healthy SSE connection.
				if tool_deltas and not emitted:
					yield ""

			reason = model._attr(choice, "finish_reason")
			if reason:
				finish_reason = reason

		usage_obj = getattr(chunk, "usage", None)
		if usage_obj is not None:
			usage = {
				"prompt_tokens": model._attr(usage_obj, "prompt_tokens", 0) or 0,
				"completion_tokens": model._attr(usage_obj, "completion_tokens", 0) or 0,
				"total_tokens": model._attr(usage_obj, "total_tokens", 0) or 0,
			}

	return model.ChatResponse(
		content="".join(content_parts) or None,
		tool_calls=model._finalize_tool_calls(tool_calls_acc),
		finish_reason=finish_reason,
		usage=usage,
	)
