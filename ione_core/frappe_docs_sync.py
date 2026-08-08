from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

DOCS_HOST = "docs.frappe.io"
SOURCE_MARKER = "IONE_FRAPPE_DOCS_SOURCE"
USER_AGENT = "I-ONE-Frappe-Docs-Sync/1.0 (+https://myyr.top)"
REQUEST_TIMEOUT = (8, 25)
DOCS_REQUEST_ATTEMPTS = 3
MAX_SOURCE_BYTES = 5 * 1024 * 1024
TRANSLATION_CHUNK_CHARACTERS = 6_000
TITLE_BATCH_SIZE = 40
TITLE_TRANSLATION_ATTEMPTS = 3
TRANSLATION_WORKERS = 4
SOURCE_FETCH_WORKERS = 4
SYNC_BATCH_SIZE = 24
MIN_TRANSLATED_BODY_CJK = 8
EMPTY_OFFICIAL_PAGE_NOTICE = "> Frappe 官方文档当前仅提供本章节标题。尚未发布正文内容。"
OFFICIAL_FALLBACK_PAGES = {
	"print-designer/introduction": {
		"title": "Print Designer",
		"markdown_url": "https://raw.githubusercontent.com/frappe/print_designer/develop/README.md",
		"source_url": "https://github.com/frappe/print_designer/blob/develop/README.md",
	}
}
PRESERVED_TITLE_WORDS = {
	"api",
	"cli",
	"crm",
	"docker",
	"erpnext",
	"exotel",
	"faq",
	"frappe",
	"github",
	"html",
	"http",
	"https",
	"javascript",
	"jinja",
	"json",
	"lms",
	"meta",
	"oauth",
	"pos",
	"python",
	"rest",
	"sdk",
	"sql",
	"twilio",
	"ui",
	"url",
	"ux",
	"webhook",
	"webhooks",
	"whatsapp",
}


@dataclass(frozen=True)
class ProductSpec:
	slug: str
	name: str
	source_prefix: str
	entry_url: str
	destination_route: str


@dataclass
class SourceNode:
	title: str
	kind: str
	source_route: str = ""
	children: list[SourceNode] = field(default_factory=list)
	identity: str = ""


@dataclass(frozen=True)
class TranslationChunk:
	text: str
	separator_before: str = ""


class TranslationInputTooLargeError(RuntimeError):
	pass


PRODUCTS: dict[str, ProductSpec] = {
	"erpnext": ProductSpec(
		"erpnext", "ERPNext 中文文档", "erpnext", "https://docs.frappe.io/erpnext/introduction", "erpnext-zh-docs"
	),
	"framework": ProductSpec(
		"framework",
		"Frappe 框架中文文档",
		"framework",
		"https://docs.frappe.io/framework/user/en/introduction",
		"framework-zh-docs",
	),
	"cloud": ProductSpec(
		"cloud", "Frappe Cloud 中文文档", "cloud", "https://docs.frappe.io/cloud/features", "cloud-zh-docs"
	),
	"hr": ProductSpec(
		"hr", "Frappe HR 中文文档", "hr", "https://docs.frappe.io/hr/introduction", "hr-zh-docs"
	),
	"learning": ProductSpec(
		"learning",
		"Frappe Learning 中文文档",
		"learning",
		"https://docs.frappe.io/learning/introduction",
		"learning-zh-docs",
	),
	"crm": ProductSpec(
		"crm", "Frappe CRM 中文文档", "crm", "https://docs.frappe.io/crm/introduction", "crm-zh-docs"
	),
	"builder": ProductSpec(
		"builder",
		"Frappe Builder 中文文档",
		"builder",
		"https://docs.frappe.io/builder/introduction",
		"builder-zh-docs",
	),
	"insights": ProductSpec(
		"insights",
		"Frappe Insights 中文文档",
		"insights",
		"https://docs.frappe.io/insights/introduction",
		"insights-zh-docs",
	),
	"education": ProductSpec(
		"education",
		"Frappe Education 中文文档",
		"education",
		"https://docs.frappe.io/education/introduction",
		"education-zh-docs",
	),
	"helpdesk": ProductSpec(
		"helpdesk",
		"Frappe Helpdesk 中文文档",
		"helpdesk",
		"https://docs.frappe.io/helpdesk/installation",
		"helpdesk-zh-docs",
	),
	"wiki": ProductSpec(
		"wiki",
		"Frappe Wiki 中文文档",
		"wiki-v2",
		"https://docs.frappe.io/wiki-v2/introduction",
		"wiki-zh-docs",
	),
	"drive": ProductSpec(
		"drive", "Frappe Drive 中文文档", "drive", "https://docs.frappe.io/drive/introduction", "drive-zh-docs"
	),
	"books": ProductSpec(
		"books", "Frappe Books 中文文档", "books", "https://docs.frappe.io/books/introduction", "books-zh-docs"
	),
	"gantt": ProductSpec(
		"gantt", "Frappe Gantt 中文文档", "gantt", "https://docs.frappe.io/gantt/introduction", "gantt-zh-docs"
	),
	"print-designer": ProductSpec(
		"print-designer",
		"Frappe Print Designer 中文文档",
		"print-designer",
		"https://docs.frappe.io/print-designer/introduction",
		"print-designer-zh-docs",
	),
	"lending": ProductSpec(
		"lending",
		"Frappe Lending 中文文档",
		"lending",
		"https://docs.frappe.io/lending/introduction",
		"lending-zh-docs",
	),
	"studio": ProductSpec(
		"studio", "Frappe Studio 中文文档", "studio", "https://docs.frappe.io/studio/introduction", "studio-zh-docs"
	),
	"customer-guide": ProductSpec(
		"customer-guide",
		"Frappe 客户指南中文文档",
		"customer-guide",
		"https://docs.frappe.io/customer-guide/introduction",
		"frappe-customer-guide-zh",
	),
	"partner-guide": ProductSpec(
		"partner-guide",
		"Frappe 合作伙伴指南中文文档",
		"partner-guide",
		"https://docs.frappe.io/partner-guide/about-frappe",
		"frappe-partner-guide-zh",
	),
}


def discover_product(spec: ProductSpec, session: Any | None = None) -> list[SourceNode]:
	import requests

	try:
		response = _docs_get(spec.entry_url, session=session)
		return parse_sidebar(response.text, spec.source_prefix)
	except (requests.RequestException, ValueError):
		fallback_routes = [
			route for route in OFFICIAL_FALLBACK_PAGES if route.startswith(f"{spec.source_prefix}/")
		]
		if not fallback_routes:
			raise
		return [
			SourceNode(
				title=str(OFFICIAL_FALLBACK_PAGES[route]["title"]),
				kind="page",
				source_route=route,
				identity=route,
			)
			for route in fallback_routes
		]


def parse_sidebar(html: str, source_prefix: str) -> list[SourceNode]:
	"""Parse the public Frappe Wiki sidebar without flattening its group hierarchy."""
	from bs4 import BeautifulSoup

	soup = BeautifulSoup(html, "html.parser")
	sidebar = soup.select_one(".wiki-sidebar")
	if sidebar is None:
		raise ValueError("The documentation page does not expose a public Wiki sidebar.")

	roots: list[SourceNode] = []
	nodes_by_tag: dict[int, SourceNode] = {}
	seen_pages: set[str] = set()
	group_number = 0
	for item in sidebar.select("li.wiki-item"):
		classes = set(item.get("class", []))
		kind = "group" if "is-group" in classes else "page" if "is-page" in classes else ""
		if not kind:
			continue

		title_element = item.select_one(".wiki-title")
		title = title_element.get_text(" ", strip=True) if title_element else ""
		control = item.select_one("[data-route]")
		route = (control.get("data-route") or "").strip("/") if control else ""
		if not title:
			continue
		if kind == "page":
			if not route.startswith(f"{source_prefix}/"):
				continue
			if route in seen_pages:
				continue
			seen_pages.add(route)

		parent_tag = item.find_parent("li", class_="wiki-item")
		parent = nodes_by_tag.get(id(parent_tag)) if parent_tag else None
		if kind == "group":
			group_number += 1
			identity = f"group:{source_prefix}:{group_number:04d}:{_safe_slug(title)}"
		else:
			identity = route
		node = SourceNode(title=title, kind=kind, source_route=route, identity=identity)
		nodes_by_tag[id(item)] = node
		if parent:
			parent.children.append(node)
		else:
			roots.append(node)

	return _prune_empty_groups(roots)


def fetch_source_page(source_route: str, session: Any | None = None) -> tuple[str, str, str]:
	import requests

	url = f"https://{DOCS_HOST}/{source_route.strip('/')}"
	try:
		response = _docs_get(url, session=session)
		title, markdown = _extract_article(response.text, response.url)
		return title, markdown, response.url
	except (requests.RequestException, ValueError) as html_error:
		# Frappe Wiki exposes the canonical source as Markdown. It is also the
		# reliable escape hatch for occasional empty HTML renders and redirect loops.
		try:
			response = _docs_get(f"{url}.md", session=session)
			title, markdown, source_url = _extract_markdown_document(response.text, url)
			return title, markdown, source_url
		except (requests.RequestException, ValueError) as markdown_error:
			fallback = OFFICIAL_FALLBACK_PAGES.get(source_route.strip("/"))
			if fallback:
				response = _official_fallback_get(str(fallback["markdown_url"]), session=session)
				body = response.text.lstrip("\ufeff").strip()
				if len(body) < 40:
					raise RuntimeError(
						f"The official fallback source for {source_route} did not contain enough content."
					) from markdown_error
				return str(fallback["title"]), body, str(fallback["source_url"])
			raise RuntimeError(
				f"Unable to read official documentation route {source_route}: "
				f"HTML failed with {html_error}; Markdown failed with {markdown_error}"
			) from markdown_error


def _extract_article(html: str, source_url: str) -> tuple[str, str]:
	from bs4 import BeautifulSoup
	from markdownify import markdownify

	soup = BeautifulSoup(html, "html.parser")
	content = soup.select_one(".prose") or soup.find("article") or soup.find("main")
	if content is None:
		raise ValueError("The documentation page did not contain readable article content.")
	for element in content.select("script, style, nav, form, button, noscript, svg"):
		element.decompose()
	for element in content.select("a[href]"):
		element["href"] = urljoin(source_url, element.get("href", ""))
	for element in content.select("img[src]"):
		element["src"] = urljoin(source_url, element.get("src", ""))

	heading = content.find("h1") or soup.find("h1")
	title = heading.get_text(" ", strip=True) if heading else ""
	if not title and soup.title:
		title = soup.title.get_text(" ", strip=True).split(" | ", 1)[0]
	markdown = markdownify(str(content), heading_style="ATX", bullets="-")
	markdown = re.sub(r"[ \t]+\n", "\n", markdown)
	markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
	if len(markdown) < 40 and not _is_heading_only_markdown(markdown):
		raise ValueError("The documentation page did not contain enough readable content.")
	return title or "Frappe Documentation", markdown


def _extract_markdown_document(markdown: str, fallback_url: str) -> tuple[str, str, str]:
	metadata: dict[str, str] = {}
	body = markdown.lstrip("\ufeff")
	frontmatter = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", body, flags=re.DOTALL)
	if frontmatter:
		for line in frontmatter.group(1).splitlines():
			key, separator, value = line.partition(":")
			if not separator:
				continue
			value = value.strip()
			if value.startswith('"') and value.endswith('"'):
				try:
					value = json.loads(value)
				except json.JSONDecodeError:
					value = value[1:-1]
			metadata[key.strip().lower()] = str(value).strip()
		body = body[frontmatter.end() :]

	body = re.sub(r"[ \t]+\n", "\n", body)
	body = re.sub(r"\n{3,}", "\n\n", body).strip()
	if len(body) < 40 and not _is_heading_only_markdown(body):
		raise ValueError("The official Markdown page did not contain enough readable content.")

	source_url = metadata.get("url") or fallback_url
	resolved = urlsplit(source_url)
	if resolved.scheme != "https" or (resolved.hostname or "").lower() != DOCS_HOST:
		raise ValueError("The official Markdown metadata referenced an untrusted source URL.")

	title = metadata.get("title") or _markdown_heading(body) or "Frappe Documentation"
	return title.strip(), _absolutize_docs_links(body), source_url


def _markdown_heading(markdown: str) -> str:
	match = re.search(r"^#\s+(.+?)\s*$", markdown, flags=re.MULTILINE)
	return match.group(1).strip() if match else ""


def _is_heading_only_markdown(markdown: str) -> bool:
	if not _markdown_heading(markdown):
		return False
	remaining = re.sub(r"(?m)^#{1,6}[ \t]+.*$", "", markdown).strip()
	return not remaining


def _absolutize_docs_links(markdown: str) -> str:
	markdown = re.sub(
		r"(\]\()/(?!/)([^)\s]+)",
		lambda match: f"{match.group(1)}https://{DOCS_HOST}/{match.group(2)}",
		markdown,
	)
	return re.sub(
		r"(\b(?:href|src)=[\"'])/(?!/)([^\"']+)",
		lambda match: f"{match.group(1)}https://{DOCS_HOST}/{match.group(2)}",
		markdown,
	)


class QwenMarkdownTranslator:
	def __init__(self, base_url: str, api_key: str, model_id: str, session: Any | None = None):
		import requests

		self.base_url = base_url.rstrip("/")
		self.api_key = api_key
		self.model_id = model_id.removeprefix("openai/")
		self.session = session or requests.Session()
		self.session.trust_env = False

	def new_worker(self) -> QwenMarkdownTranslator:
		"""Create a translator with an isolated HTTP session for worker threads."""
		return QwenMarkdownTranslator(self.base_url, self.api_key, self.model_id)

	@classmethod
	def from_flow_model(
		cls,
		model_name: str | None = None,
		base_url_override: str | None = None,
	) -> QwenMarkdownTranslator:
		from ione_core.translation_catalog import _get_flow_model

		model = _get_flow_model(model_name)
		base_url = (base_url_override or model.base_url or "").strip()
		if not base_url:
			raise ValueError("The selected Flow Model has no base URL.")
		return cls(base_url, model.get_password("api_key"), model.model_id)

	def translate_titles(self, titles: Iterable[str]) -> dict[str, str]:
		unique_titles = list(dict.fromkeys(title for title in titles if title))
		batches = [
			unique_titles[offset : offset + TITLE_BATCH_SIZE]
			for offset in range(0, len(unique_titles), TITLE_BATCH_SIZE)
		]
		if len(batches) <= 1:
			return self._translate_title_batch(batches[0]) if batches else {}

		translations: dict[str, str] = {}
		with ThreadPoolExecutor(max_workers=min(TRANSLATION_WORKERS, len(batches))) as executor:
			for translated_batch in executor.map(
				lambda batch: self.new_worker()._translate_title_batch(batch), batches
			):
				translations.update(translated_batch)
		return translations

	def _translate_title_batch(self, batch: list[str]) -> dict[str, str]:
		translations: dict[str, str] = {}
		if batch:
			pending = dict(enumerate(batch))
			by_id: dict[int, str] = {}
			for attempt in range(TITLE_TRANSLATION_ATTEMPTS):
				rows = [{"id": index, "title": title} for index, title in pending.items()]
				prompt = (
					"将下面的 Frappe 官方文档章节标题翻译为自然、准确、简洁的简体中文。"
					"保留 ERPNext、Frappe、API、DocType、SQL、GitHub 等产品和技术名称。"
					"必须返回全部 id, 且只返回 JSON 数组。每项格式为 "
					'{"id":整数,"translation":"译文"}。\n' + json.dumps(rows, ensure_ascii=False)
				)
				try:
					resolved = _extract_title_translations(self._chat(prompt), set(pending))
					resolved = {
						index: translation
						for index, translation in resolved.items()
						if not _is_probably_untranslated_title(pending[index], translation)
					}
				except (TypeError, ValueError, json.JSONDecodeError):
					resolved = {}
				by_id.update(resolved)
				pending = {index: title for index, title in pending.items() if index not in resolved}
				if not pending:
					break
				if attempt + 1 < TITLE_TRANSLATION_ATTEMPTS:
					time.sleep(2**attempt)

			for index, title in pending.items():
				translated = ""
				for attempt in range(TITLE_TRANSLATION_ATTEMPTS):
					prompt = (
						"把下面这个 Frappe 官方文档标题翻译成简洁、自然的简体中文。"
						"保留产品名和技术名, 只返回译文本身, 不要解释:\n" + title
					)
					if attempt:
						prompt += "\n上一次仍是英文。请给出中文标题。"
					translated = _clean_single_title_translation(self._chat(prompt))
					if translated and not _is_probably_untranslated_title(title, translated):
						break
					if attempt + 1 < TITLE_TRANSLATION_ATTEMPTS:
						time.sleep(2**attempt)
				by_id[index] = translated or title
			translations.update({source: by_id[index] for index, source in enumerate(batch)})
		return translations

	def translate_markdown(self, markdown: str) -> str:
		protected, literals = _protect_markdown_literals(markdown)
		chunks = _split_markdown(protected, TRANSLATION_CHUNK_CHARACTERS)
		translated_chunks = []
		for index, chunk in enumerate(chunks, start=1):
			translated_chunks.append(
				chunk.separator_before
				+ self._translate_markdown_chunk_resilient(chunk.text, index, len(chunks))
			)
		translated = "".join(translated_chunks)
		return _restore_markdown_literals(translated, literals)

	def _translate_markdown_chunk_resilient(
		self,
		text: str,
		index: int,
		total: int,
		depth: int = 0,
	) -> str:
		try:
			return self._translate_markdown_chunk(text, index, total)
		except (ValueError, TranslationInputTooLargeError):
			if depth >= 3 or len(text) < 600:
				raise
			subchunks = _split_markdown(text, max(300, len(text) // 2))
			if len(subchunks) < 2:
				raise
			return "".join(
				chunk.separator_before
				+ self._translate_markdown_chunk_resilient(
					chunk.text, subindex, len(subchunks), depth + 1
				)
				for subindex, chunk in enumerate(subchunks, start=1)
			)

	def _translate_markdown_chunk(self, text: str, index: int, total: int) -> str:
		required_literals = _protected_literal_tokens(text)
		last_error = ""
		for attempt in range(TITLE_TRANSLATION_ATTEMPTS):
			prompt = (
				f"这是同一篇 Frappe 官方技术文档的第 {index}/{total} 段。"
				"请完整翻译为专业、自然的简体中文。保持 Markdown 层级、列表、表格、链接、图片、"
				"HTML 标签和 [[[IONE_LITERAL_数字]]] 占位符完全不变。保留产品名、命令、字段名、"
				"API、DocType、路径和参数。不要概括、删减或解释。不要包裹新的代码围栏。"
			)
			if required_literals:
				prompt += "以下占位符必须各原样出现一次: " + ", ".join(required_literals) + "。"
			if attempt:
				prompt += f"上一次结果的占位符校验失败: {last_error}。请重新完整翻译。"
			translated = self._chat(prompt + "\n\n" + text).strip()
			actual_literals = _protected_literal_tokens(translated)
			fidelity_issues = _translation_fidelity_issues(text, translated)
			if actual_literals == required_literals and not fidelity_issues:
				return translated
			problems = []
			if actual_literals != required_literals:
				problems.append(f"expected literals {required_literals}, got {actual_literals}")
			if fidelity_issues:
				problems.append("structure " + "; ".join(fidelity_issues))
			last_error = "; ".join(problems)
			if attempt + 1 < TITLE_TRANSLATION_ATTEMPTS:
				time.sleep(2**attempt)
		raise ValueError(f"The translated Markdown did not preserve source fidelity: {last_error}")

	def _chat(self, prompt: str) -> str:
		headers = {"Content-Type": "application/json"}
		if self.api_key:
			headers["Authorization"] = f"Bearer {self.api_key}"
		payload: dict[str, Any] = {
			"model": self.model_id,
			"temperature": 0,
			"max_tokens": 8192,
			"chat_template_kwargs": {"enable_thinking": False},
			"messages": [
				{
					"role": "system",
					"content": "你是 I-ONE 的 Frappe 官方文档简体中文翻译编辑。忠于原文并严格保持技术格式。",
				},
				{"role": "user", "content": prompt},
			],
		}
		last_error: Exception | None = None
		for attempt in range(3):
			try:
				response = self.session.post(
					f"{self.base_url}/chat/completions",
					headers=headers,
					json=payload,
					timeout=330,
				)
				if getattr(response, "status_code", None) == 400:
					detail = str(getattr(response, "text", ""))[:1_000]
					if "context length" in detail.casefold() or "maximum context" in detail.casefold():
						raise TranslationInputTooLargeError(
							f"Qwen rejected an oversized translation request: {detail}"
						)
				response.raise_for_status()
				content = response.json()["choices"][0]["message"]["content"].strip()
				return _strip_outer_fence(content)
			except TranslationInputTooLargeError:
				raise
			except Exception as exc:
				last_error = exc
				time.sleep(2**attempt)
		raise RuntimeError(f"Qwen document translation failed: {last_error}")


def sync_frappe_docs(
	products: list[str] | str | None = None,
	force: bool = False,
	max_pages_per_product: int = 0,
	model_name: str | None = None,
	base_url_override: str | None = None,
) -> dict[str, Any]:
	"""Synchronize selected official documentation spaces into the current site Wiki."""
	import frappe
	import requests

	if "wiki" not in frappe.get_installed_apps():
		frappe.throw("Frappe Wiki must be installed before documentation can be synchronized.")
	selected = _normalize_products(products)
	translator = QwenMarkdownTranslator.from_flow_model(model_name, base_url_override)
	session = requests.Session()
	session.trust_env = False
	session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html"})
	results: dict[str, Any] = {}
	for slug in selected:
		try:
			results[slug] = _sync_product(
				PRODUCTS[slug],
				translator,
				session,
				force=force,
				max_pages=max_pages_per_product,
			)
		except Exception as exc:
			frappe.log_error(title=f"Frappe docs sync failed: {slug}", message=frappe.get_traceback())
			results[slug] = {"status": "failed", "error": str(exc)}
		_write_progress(results)
	return results


def enqueue_frappe_docs_sync(
	products: list[str] | str | None = None,
	force: bool = False,
	max_pages_per_product: int = 0,
	model_name: str | None = None,
	base_url_override: str | None = None,
) -> dict[str, Any]:
	"""Queue the resumable synchronizer without holding an HTTP request open."""
	import frappe

	selected = _normalize_products(products)
	job = frappe.enqueue(
		"ione_core.frappe_docs_sync.sync_frappe_docs",
		queue="long",
		timeout=24 * 60 * 60,
		job_name=f"frappe-docs-zh-{'-'.join(selected)}",
		products=selected,
		force=force,
		max_pages_per_product=max_pages_per_product,
		model_name=model_name,
		base_url_override=base_url_override,
	)
	return {"queued": True, "job_id": job.id, "products": selected}


def repair_frappe_docs_public_access(
	products: list[str] | str | None = None,
) -> dict[str, Any]:
	"""Repair public read access and legacy editor-SPA links without retranslating pages."""
	import frappe

	selected = _normalize_products(products)
	results: dict[str, Any] = {}
	for slug in selected:
		spec = PRODUCTS[slug]
		space_name = frappe.db.get_value("Wiki Space", {"route": spec.destination_route}, "name")
		if not space_name:
			results[slug] = {"status": "missing"}
			continue

		space = frappe.get_doc("Wiki Space", space_name)
		roles_added = _ensure_public_read_roles(space)
		if roles_added:
			space.save(ignore_permissions=True)

		documents = frappe.get_all(
			"Wiki Document",
			filters={"wiki_space": space_name, "is_group": 0},
			fields=["name", "content"],
			limit_page_length=0,
		)
		links_repaired = 0
		for document in documents:
			content = document.content or ""
			repaired = _rewrite_legacy_wiki_links(content, {})
			if repaired == content:
				continue
			frappe.db.set_value(
				"Wiki Document", document.name, "content", repaired, update_modified=False
			)
			links_repaired += 1

		frappe.db.commit()
		results[slug] = {
			"status": "repaired",
			"wiki_space": space_name,
			"public_roles_added": roles_added,
			"links_repaired": links_repaired,
		}

	frappe.cache().delete_value("wiki_public_tree")
	frappe.clear_cache()
	frappe.db.commit()
	return results


def audit_frappe_docs(
	products: list[str] | str | None = None,
	verify_source_content: bool = False,
) -> dict[str, Any]:
	"""Compare the live official chapter trees with their synchronized Wiki spaces."""
	import frappe
	import requests

	selected = _normalize_products(products)
	session = requests.Session()
	session.trust_env = False
	session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html"})
	results: dict[str, Any] = {}
	for slug in selected:
		spec = PRODUCTS[slug]
		try:
			tree = discover_product(spec, session=session)
		except Exception as exc:
			results[slug] = {"status": "source_unavailable", "error": str(exc)}
			continue

		expected = _expected_source_hierarchy(spec, tree)
		space_name = frappe.db.get_value("Wiki Space", {"route": spec.destination_route}, "name")
		if not space_name:
			results[slug] = {
				"status": "missing",
				"source_pages": sum(1 for node in expected.values() if node["kind"] == "page"),
				"source_groups": sum(1 for node in expected.values() if node["kind"] == "group") - 1,
			}
			continue
		public_read_roles = set(
			frappe.get_all(
				"Wiki Space Role",
				filters={
					"parent": space_name,
					"parenttype": "Wiki Space",
					"permission_level": "Read",
				},
				pluck="role",
			)
		)

		documents = frappe.get_all(
			"Wiki Document",
			filters={"wiki_space": space_name},
			fields=[
				"name",
				"title",
				"source_path",
				"route",
				"is_group",
				"is_published",
				"parent_wiki_document",
				"content",
			],
		)
		by_source: dict[str, list[Any]] = {}
		name_to_source = {document.name: document.source_path for document in documents}
		unmanaged = []
		for document in documents:
			if document.source_path:
				by_source.setdefault(document.source_path, []).append(document)
			else:
				unmanaged.append(document.name)

		missing = sorted(set(expected) - set(by_source))
		duplicates = sorted(source for source, matches in by_source.items() if len(matches) > 1)
		extra = sorted(set(by_source) - set(expected))
		hierarchy_mismatches = []
		route_mismatches = []
		unpublished = []
		missing_source_markers = []
		low_chinese_content = []
		untranslated_titles = []
		bad_internal_links = []
		stale_source = []
		source_fetch_errors = []
		fidelity_issues = []
		source_checks: list[tuple[str, str]] = []
		for source_path, expectation in expected.items():
			matches = by_source.get(source_path, [])
			if len(matches) != 1:
				continue
			document = matches[0]
			actual_parent = name_to_source.get(document.parent_wiki_document)
			if actual_parent != expectation["parent"]:
				hierarchy_mismatches.append(source_path)
			if document.route != expectation["route"]:
				route_mismatches.append(source_path)
			if not document.is_published:
				unpublished.append(source_path)
			if source_path != f"root:{spec.slug}" and _is_probably_untranslated_title(
				expectation.get("title", ""), document.title or ""
			):
				untranslated_titles.append(source_path)
			if expectation["kind"] != "page":
				continue
			content = document.content or ""
			if SOURCE_MARKER not in content:
				missing_source_markers.append(source_path)
			if len(re.findall(r"[\u3400-\u9fff]", _translated_markdown_body(content))) < MIN_TRANSLATED_BODY_CJK:
				low_chinese_content.append(source_path)
			if f"/wiki/{spec.destination_route}" in content:
				bad_internal_links.append(source_path)
			if verify_source_content:
				source_checks.append((source_path, content))

		if source_checks:
			with ThreadPoolExecutor(max_workers=SOURCE_FETCH_WORKERS) as executor:
				fetch_futures = {
					source_path: executor.submit(fetch_source_page, source_path)
					for source_path, _content in source_checks
				}
				for source_path, content in source_checks:
					try:
						source_title, source_markdown, _source_url = fetch_futures[
							source_path
						].result()
					except Exception as exc:
						source_fetch_errors.append(
							{"source_path": source_path, "error": str(exc)}
						)
						continue
					if _content_source_hash(content) != _source_hash(source_title, source_markdown):
						stale_source.append(source_path)
					page_fidelity_issues = _translation_fidelity_issues(
						source_markdown, _translated_markdown_body(content)
					)
					if page_fidelity_issues:
						fidelity_issues.append(
							{"source_path": source_path, "issues": page_fidelity_issues}
						)

		issues = {
			"missing_read_roles": sorted({"All", "Guest"} - public_read_roles),
			"missing": missing,
			"duplicates": duplicates,
			"extra_managed": extra,
			"unmanaged": sorted(unmanaged),
			"hierarchy_mismatches": sorted(hierarchy_mismatches),
			"route_mismatches": sorted(route_mismatches),
			"unpublished": sorted(unpublished),
			"missing_source_markers": sorted(missing_source_markers),
			"low_chinese_content": sorted(low_chinese_content),
			"untranslated_titles": sorted(untranslated_titles),
			"bad_internal_links": sorted(bad_internal_links),
			"stale_source": sorted(stale_source),
			"source_fetch_errors": source_fetch_errors,
			"fidelity_issues": fidelity_issues,
		}
		results[slug] = {
			"status": "passed" if not any(issues.values()) else "needs_attention",
			"wiki_space": space_name,
			"source_pages": sum(1 for node in expected.values() if node["kind"] == "page"),
			"wiki_pages": sum(1 for document in documents if not document.is_group),
			"source_groups": sum(1 for node in expected.values() if node["kind"] == "group") - 1,
			"wiki_groups": sum(1 for document in documents if document.is_group) - 1,
			"issues": issues,
		}
	return results


def _sync_product(
	spec: ProductSpec,
	translator: QwenMarkdownTranslator,
	session: Any,
	force: bool,
	max_pages: int,
) -> dict[str, Any]:
	import frappe

	tree = discover_product(spec, session=session)
	pages = list(_iter_pages(tree))
	if max_pages:
		allowed_routes = {node.source_route for node in pages[:max_pages]}
		tree = _filter_tree_to_routes(tree, allowed_routes)
		pages = list(_iter_pages(tree))
	if not pages:
		raise ValueError(f"No public documentation pages were discovered for {spec.slug}.")

	titles = translator.translate_titles(node.title for node in _walk_nodes(tree))
	root, space = _ensure_space(spec)
	route_map = {
		node.source_route: _destination_route(spec, node.source_route)
		for node in pages
	}
	stats = {
		"status": "running",
		"discovered": len(pages),
		"created": 0,
		"updated": 0,
		"skipped": 0,
		"failed": 0,
	}
	page_jobs: list[dict[str, Any]] = []
	failures: list[dict[str, str]] = []

	def prepare_nodes(nodes: list[SourceNode], parent_name: str) -> None:
		for sort_order, node in enumerate(nodes):
			translated_title = titles.get(node.title, node.title)
			if node.kind == "group":
				group = _upsert_group(
					spec, node, translated_title, parent_name, space.name, sort_order
				)
				prepare_nodes(node.children, group.name)
				continue

			destination_route = route_map[node.source_route]
			existing = _find_managed_document(space.name, node.source_route, destination_route, False)
			page_jobs.append(
				{
					"node": node,
					"translated_title": translated_title,
					"parent_name": parent_name,
					"sort_order": sort_order,
					"destination_route": destination_route,
					"existing": existing,
				}
			)

	prepare_nodes(tree, root.name)
	frappe.db.commit()

	with (
		ThreadPoolExecutor(max_workers=SOURCE_FETCH_WORKERS) as fetch_executor,
		ThreadPoolExecutor(max_workers=TRANSLATION_WORKERS) as translation_executor,
	):
		for offset in range(0, len(page_jobs), SYNC_BATCH_SIZE):
			batch = page_jobs[offset : offset + SYNC_BATCH_SIZE]
			fetch_futures = {
				job["node"].source_route: fetch_executor.submit(
					fetch_source_page, job["node"].source_route
				)
				for job in batch
			}
			prepared_batch: list[dict[str, Any]] = []
			for job in batch:
				node = job["node"]
				try:
					source_title, source_markdown, source_url = fetch_futures[
						node.source_route
					].result()
				except Exception as exc:
					failures.append({"source_route": node.source_route, "error": str(exc)})
					stats["failed"] += 1
					_write_progress(
						{
							spec.slug: {
								**stats,
								"last_source_route": node.source_route,
								"last_error": str(exc),
							}
						}
					)
					continue

				source_hash = _source_hash(source_title, source_markdown)
				existing = job["existing"]
				source_current = bool(
					existing
					and not force
					and _content_source_hash(existing.content or "") == source_hash
				)
				content = ""
				current = False
				if source_current:
					content = _rewrite_legacy_wiki_links(existing.content or "", route_map)
					current = content == (existing.content or "")
				job.update(
					{
						"source_markdown": source_markdown,
						"source_url": source_url,
						"source_hash": source_hash,
						"content": content,
						"current": current,
						"needs_translation": not source_current,
					}
				)
				prepared_batch.append(job)

			translation_futures: dict[str, Future[str]] = {}
			for job in prepared_batch:
				if not job["needs_translation"]:
					continue
				node = job["node"]
				translation_futures[node.source_route] = translation_executor.submit(
					_translate_page_content,
					translator,
					job["source_markdown"],
					job["source_url"],
					job["source_hash"],
					route_map,
				)

			for job in prepared_batch:
				node = job["node"]
				if job["needs_translation"]:
					try:
						job["content"] = translation_futures[node.source_route].result()
					except Exception as exc:
						failures.append({"source_route": node.source_route, "error": str(exc)})
						stats["failed"] += 1
						_write_progress(
							{
								spec.slug: {
									**stats,
									"last_source_route": node.source_route,
									"last_error": str(exc),
								}
							}
						)
						continue

				created = job["existing"] is None
				_upsert_page(
					spec,
					node,
					job["translated_title"],
					job["parent_name"],
					space.name,
					job["sort_order"],
					job["destination_route"],
					job["content"],
					job["existing"],
				)
				if job["current"]:
					stats["skipped"] += 1
				else:
					stats["created" if created else "updated"] += 1
				frappe.db.commit()
				_write_progress({spec.slug: {**stats, "last_source_route": node.source_route}})

	stats["status"] = "partial" if failures else "completed"
	if failures:
		stats["failures"] = failures
	stats["wiki_space"] = space.name
	stats["route"] = spec.destination_route
	frappe.clear_cache()
	frappe.db.commit()
	return stats


def _translate_page_content(
	translator: QwenMarkdownTranslator,
	source_markdown: str,
	source_url: str,
	source_hash: str,
	route_map: dict[str, str],
) -> str:
	translated_markdown = translator.new_worker().translate_markdown(source_markdown)
	if _is_heading_only_markdown(source_markdown):
		translated_markdown = f"{translated_markdown.rstrip()}\n\n{EMPTY_OFFICIAL_PAGE_NOTICE}"
	translated_markdown = _rewrite_internal_links(translated_markdown, route_map)
	return _build_published_content(translated_markdown, source_url, source_hash)


def _ensure_space(spec: ProductSpec):
	import frappe

	space_name = frappe.db.get_value("Wiki Space", {"route": spec.destination_route}, "name")
	space = frappe.get_doc("Wiki Space", space_name) if space_name else None
	root = frappe.get_doc("Wiki Document", space.root_group) if space and space.root_group else None
	if root is None:
		root = frappe.get_doc(
			{
				"doctype": "Wiki Document",
				"title": spec.name.removesuffix(" 中文文档"),
				"slug": spec.destination_route,
				"route": spec.destination_route,
				"is_group": 1,
				"is_published": 1,
				"source_path": f"root:{spec.slug}",
			}
		).insert(ignore_permissions=True)
	if space is None:
		space = frappe.get_doc(
			{
				"doctype": "Wiki Space",
				"space_name": spec.name,
				"route": spec.destination_route,
				"root_group": root.name,
				"is_published": 1,
				"show_in_switcher": 1,
				"allow_contributions": 1,
			}
		)
		_ensure_public_read_roles(space)
		space.insert(ignore_permissions=True)
	else:
		space.update(
			{
				"space_name": spec.name,
				"root_group": root.name,
				"is_published": 1,
				"show_in_switcher": 1,
			}
		)
		_ensure_public_read_roles(space)
		space.save(ignore_permissions=True)
	root.update(
		{
			"title": spec.name.removesuffix(" 中文文档"),
			"slug": spec.destination_route,
			"route": spec.destination_route,
			"source_path": f"root:{spec.slug}",
			"wiki_space": space.name,
			"is_published": 1,
		}
	)
	root.save(ignore_permissions=True)
	frappe.db.commit()
	return root, space


def _ensure_public_read_roles(space: Any) -> list[str]:
	existing = {
		row.role
		for row in (space.get("roles") or [])
		if row.permission_level == "Read"
	}
	added = []
	for role in ("Guest", "All"):
		if role in existing:
			continue
		space.append("roles", {"role": role, "permission_level": "Read"})
		added.append(role)
	return added


def _upsert_group(
	spec: ProductSpec,
	node: SourceNode,
	title: str,
	parent: str,
	space: str,
	sort_order: int,
):
	import frappe

	route = _group_route(spec, node)
	doc = _find_managed_document(space, node.identity, route, True)
	values = {
		"title": title,
		"slug": _safe_slug(node.title),
		"route": route,
		"source_path": node.identity,
		"is_group": 1,
		"is_published": 1,
		"parent_wiki_document": parent,
		"wiki_space": space,
		"sort_order": sort_order,
	}
	if doc:
		if doc.parent_wiki_document != parent:
			doc.old_parent = doc.parent_wiki_document
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": "Wiki Document", **values}).insert(ignore_permissions=True)
	frappe.db.set_value("Wiki Document", doc.name, "sort_order", sort_order, update_modified=False)
	return doc


def _upsert_page(
	spec: ProductSpec,
	node: SourceNode,
	title: str,
	parent: str,
	space: str,
	sort_order: int,
	route: str,
	content: str,
	existing: Any | None,
):
	import frappe

	doc = existing or _find_managed_document(space, node.source_route, route, False)
	values = {
		"title": title,
		"slug": route.rsplit("/", 1)[-1],
		"route": route,
		"source_path": node.source_route,
		"content": content,
		"is_group": 0,
		"is_published": 1,
		"parent_wiki_document": parent,
		"wiki_space": space,
		"sort_order": sort_order,
	}
	if doc:
		if doc.parent_wiki_document != parent:
			doc.old_parent = doc.parent_wiki_document
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": "Wiki Document", **values}).insert(ignore_permissions=True)
	frappe.db.set_value("Wiki Document", doc.name, "sort_order", sort_order, update_modified=False)
	return doc


def _find_managed_document(space: str, source_path: str, route: str, is_group: bool):
	import frappe

	name = frappe.db.get_value(
		"Wiki Document",
		{"wiki_space": space, "source_path": source_path, "is_group": int(is_group)},
		"name",
	)
	if not name:
		name = frappe.db.get_value(
			"Wiki Document",
			{"wiki_space": space, "route": route, "is_group": int(is_group)},
			"name",
		)
	return frappe.get_doc("Wiki Document", name) if name else None


def _docs_get(url: str, session: Any | None = None):
	import requests

	parsed = urlsplit(url)
	if parsed.scheme != "https" or (parsed.hostname or "").lower() != DOCS_HOST:
		raise ValueError("Only public HTTPS pages on docs.frappe.io can be synchronized.")
	session = session or requests.Session()
	session.trust_env = False
	session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9"})
	last_error: requests.RequestException | None = None
	for attempt in range(DOCS_REQUEST_ATTEMPTS):
		try:
			response = session.get(url, timeout=REQUEST_TIMEOUT)
			response.raise_for_status()
			break
		except requests.RequestException as exc:
			last_error = exc
			if isinstance(exc, requests.TooManyRedirects):
				raise
			if attempt + 1 == DOCS_REQUEST_ATTEMPTS:
				raise
			time.sleep(2**attempt)
	else:
		raise RuntimeError(f"Frappe documentation request failed: {last_error}")
	if len(response.content) > MAX_SOURCE_BYTES:
		raise ValueError("The documentation page is larger than the allowed source size.")
	resolved = urlsplit(response.url)
	if resolved.scheme != "https" or (resolved.hostname or "").lower() != DOCS_HOST:
		raise ValueError("The documentation request redirected outside docs.frappe.io.")
	return response


def _official_fallback_get(url: str, session: Any | None = None):
	import requests

	allowed_url = str(OFFICIAL_FALLBACK_PAGES["print-designer/introduction"]["markdown_url"])
	if url != allowed_url:
		raise ValueError("The requested documentation fallback is not trusted.")
	session = session or requests.Session()
	session.trust_env = False
	session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/plain"})
	response = session.get(url, timeout=REQUEST_TIMEOUT)
	response.raise_for_status()
	if len(response.content) > MAX_SOURCE_BYTES:
		raise ValueError("The documentation fallback is larger than the allowed source size.")
	resolved = urlsplit(response.url)
	if resolved.scheme != "https" or resolved.hostname != "raw.githubusercontent.com":
		raise ValueError("The documentation fallback redirected to an untrusted host.")
	return response


def _destination_route(spec: ProductSpec, source_route: str) -> str:
	prefix = f"{spec.source_prefix}/"
	relative = source_route[len(prefix) :] if source_route.startswith(prefix) else source_route
	return f"{spec.destination_route}/{relative.strip('/')}"


def _group_route(spec: ProductSpec, node: SourceNode) -> str:
	"""Give sidebar groups routes that cannot collide with their landing pages."""
	return f"{spec.destination_route}/_section/{node.identity.split(':')[2]}"


def _expected_source_hierarchy(spec: ProductSpec, tree: list[SourceNode]) -> dict[str, dict[str, Any]]:
	expected: dict[str, dict[str, Any]] = {
		f"root:{spec.slug}": {
			"kind": "group",
			"parent": None,
			"route": spec.destination_route,
			"title": spec.name,
		}
	}

	def collect(nodes: list[SourceNode], parent: str) -> None:
		for node in nodes:
			source_path = node.identity if node.kind == "group" else node.source_route
			route = (
				_group_route(spec, node)
				if node.kind == "group"
				else _destination_route(spec, node.source_route)
			)
			expected[source_path] = {
				"kind": node.kind,
				"parent": parent,
				"route": route,
				"title": node.title,
			}
			if node.kind == "group":
				collect(node.children, source_path)

	collect(tree, f"root:{spec.slug}")
	return expected


def _rewrite_internal_links(markdown: str, route_map: dict[str, str]) -> str:
	for source_route, destination_route in sorted(route_map.items(), key=lambda item: len(item[0]), reverse=True):
		markdown = markdown.replace(
			f"https://{DOCS_HOST}/{source_route}", f"/{destination_route}"
		)
	return _rewrite_legacy_wiki_links(markdown, route_map)


def _rewrite_legacy_wiki_links(markdown: str, route_map: dict[str, str]) -> str:
	"""Point old editor-SPA links at Wiki's public root-route reader."""
	root_routes = {spec.destination_route for spec in PRODUCTS.values()}
	root_routes.update(route.split("/", 1)[0] for route in route_map.values())
	for root_route in sorted(root_routes, key=len, reverse=True):
		markdown = markdown.replace(f"/wiki/{root_route}", f"/{root_route}")
	return markdown


def _build_published_content(markdown: str, source_url: str, source_hash: str) -> str:
	resolved = urlsplit(source_url)
	source_label = "Frappe 官方文档" if resolved.hostname == DOCS_HOST else "Frappe 官方项目说明"
	return (
		f"<!-- {SOURCE_MARKER}\nsource_url: {source_url}\nsource_hash: {source_hash}\n-->\n\n"
		f"> 本页译自 [{source_label}]({source_url})。内容与官方章节保持同步。\n\n"
		f"{markdown.strip()}\n"
	)


def _translated_markdown_body(content: str) -> str:
	content = re.sub(rf"<!-- {SOURCE_MARKER}\b.*?-->\s*", "", content, count=1, flags=re.DOTALL)
	return re.sub(
		r"^> 本页译自 \[Frappe 官方(?:文档|项目说明)\]\([^\n]+\)。内容与官方章节保持同步。\s*",
		"",
		content,
		count=1,
	).strip()


def _translation_fidelity_issues(source: str, translated: str) -> list[str]:
	"""Return conservative signals that a translation lost source structure or prose."""
	issues = []
	checks = {
		"headings": r"(?m)^#{1,6}[ \t]+\S",
		"code_fences": r"(?m)^[ \t]*(?:```|~~~)",
		"images": r"!\[[^\]]*\]\(",
		"table_rows": r"(?m)^[ \t]*\|.*\|[ \t]*$",
		"list_items": r"(?m)^[ \t]*(?:[-+*]|\d+[.)])[ \t]+\S",
		"blockquotes": r"(?m)^[ \t]*>[ \t]",
	}
	for label, pattern in checks.items():
		source_count = len(re.findall(pattern, source))
		translated_count = len(re.findall(pattern, translated))
		if translated_count < source_count:
			issues.append(f"{label}: expected at least {source_count}, got {translated_count}")

	source_length = _markdown_prose_length(source)
	translated_length = _markdown_prose_length(translated)
	if source_length >= 200 and translated_length < source_length * 0.2:
		issues.append(
			f"prose_length: expected at least {int(source_length * 0.2)}, got {translated_length}"
		)
	return issues


def _markdown_prose_length(markdown: str) -> int:
	text = re.sub(r"```[^\n]*\n.*?```|~~~[^\n]*\n.*?~~~", "", markdown, flags=re.DOTALL)
	text = re.sub(r"`[^`\n]+`", "", text)
	text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
	text = re.sub(r"https?://\S+|<[^>]+>", "", text)
	return len(re.findall(r"[A-Za-z0-9\u3400-\u9fff]", text))


def _is_probably_untranslated_title(source_title: str, translated_title: str) -> bool:
	if source_title.strip().casefold() != translated_title.strip().casefold():
		return False
	if re.search(r"[\u3400-\u9fff]", translated_title):
		return False
	words = re.findall(r"[A-Za-z][A-Za-z0-9.+#-]*", translated_title.casefold())
	return bool(words) and any(word not in PRESERVED_TITLE_WORDS for word in words)


def _source_hash(title: str, markdown: str) -> str:
	stable_markdown = re.sub(
		r"(?<=/cdn-cgi/l/email-protection#)[0-9a-fA-F]+",
		"protected",
		markdown,
	)
	return hashlib.sha256(f"{title}\n{stable_markdown}".encode()).hexdigest()


def _content_source_hash(content: str) -> str:
	match = re.search(rf"<!-- {SOURCE_MARKER}\b.*?\nsource_hash:\s*([0-9a-f]{{64}})\s*\n-->", content, re.DOTALL)
	return match.group(1) if match else ""


def _protect_markdown_literals(markdown: str) -> tuple[str, list[str]]:
	literals: list[str] = []
	pattern = re.compile(
		r"```[^\n]*\n.*?```|~~~[^\n]*\n.*?~~~|^[ \t]*(?:#{1,6}[ \t]+|(?:>[ \t]*)+)|"
		r"`[^`\n]+`|(?<=\()https?://[^)\s]+(?=\))|</?[A-Za-z][^>\n]*>",
		re.DOTALL | re.MULTILINE,
	)

	def replace(match: re.Match[str]) -> str:
		index = len(literals)
		literals.append(match.group(0))
		return f"[[[IONE_LITERAL_{index:04d}]]]"

	return pattern.sub(replace, markdown), literals


def _restore_markdown_literals(markdown: str, literals: list[str]) -> str:
	for index, literal in enumerate(literals):
		placeholder = f"[[[IONE_LITERAL_{index:04d}]]]"
		if placeholder not in markdown:
			raise ValueError(f"The translated Markdown lost protected literal {placeholder}.")
		markdown = markdown.replace(placeholder, literal)
	if re.search(r"\[\[\[IONE_LITERAL_\d+\]\]\]", markdown):
		raise ValueError("The translated Markdown contains an unknown protected literal.")
	return markdown


def _protected_literal_tokens(markdown: str) -> list[str]:
	return sorted(re.findall(r"\[\[\[IONE_LITERAL_\d+\]\]\]", markdown))


def _split_markdown(markdown: str, maximum: int) -> list[TranslationChunk]:
	parts = re.split(r"(\n{2,})", markdown.strip())
	blocks: list[tuple[str, str]] = []
	separator = ""
	for part in parts:
		if not part:
			continue
		if re.fullmatch(r"\n{2,}", part):
			separator = part
			continue
		blocks.append((separator, part))
		separator = ""

	chunks: list[TranslationChunk] = []
	current_text = ""
	current_separator = ""

	def flush() -> None:
		nonlocal current_text, current_separator
		if current_text:
			chunks.append(TranslationChunk(current_text, current_separator))
			current_text = ""
			current_separator = ""

	for block_separator, block in blocks:
		if len(block) <= maximum:
			addition = (block_separator if current_text else "") + block
			if current_text and len(current_text) + len(addition) > maximum:
				flush()
				current_separator = block_separator
				current_text = block
			else:
				if not current_text:
					current_separator = block_separator
				current_text += addition
			continue

		flush()
		lines = block.split("\n")
		line_text = ""
		line_separator = block_separator
		for line in lines:
			addition = ("\n" if line_text else "") + line
			if line_text and len(line_text) + len(addition) > maximum:
				chunks.append(TranslationChunk(line_text, line_separator))
				line_text = line
				line_separator = "\n"
			else:
				line_text += addition
		if line_text:
			chunks.append(TranslationChunk(line_text, line_separator))

	flush()
	bounded: list[TranslationChunk] = []
	for chunk in chunks:
		if len(chunk.text) <= maximum:
			bounded.append(chunk)
			continue
		parts = _hard_split_text(chunk.text, maximum)
		parts[0] = TranslationChunk(parts[0].text, chunk.separator_before + parts[0].separator_before)
		bounded.extend(parts)
	return bounded or [TranslationChunk("")]


def _hard_split_text(text: str, maximum: int) -> list[TranslationChunk]:
	"""Bound an indivisible Markdown line while preserving its exact separators."""
	parts: list[TranslationChunk] = []
	separator = ""
	remaining = text
	while len(remaining) > maximum:
		window = remaining[: maximum + 1]
		matches = list(re.finditer(r"\s+", window))
		boundary = next(
			(match for match in reversed(matches) if match.start() >= maximum // 2),
			None,
		)
		if boundary:
			parts.append(TranslationChunk(remaining[: boundary.start()], separator))
			separator = boundary.group(0)
			remaining = remaining[boundary.end() :]
		else:
			parts.append(TranslationChunk(remaining[:maximum], separator))
			separator = ""
			remaining = remaining[maximum:]
	if remaining or separator:
		parts.append(TranslationChunk(remaining, separator))
	return parts


def _parse_json_array(content: str) -> list[dict[str, Any]]:
	content = _strip_outer_fence(content)
	start = content.find("[")
	end = content.rfind("]")
	if start < 0 or end < start:
		raise ValueError("The translation response did not contain a JSON array.")
	value = json.loads(content[start : end + 1])
	if not isinstance(value, list):
		raise ValueError("The translation response was not a JSON array.")
	return value


def _extract_title_translations(content: str, expected_ids: set[int]) -> dict[int, str]:
	translations: dict[int, str] = {}
	for row in _parse_json_array(content):
		if not isinstance(row, dict):
			continue
		try:
			row_id = int(row.get("id"))
		except (TypeError, ValueError):
			continue
		if row_id not in expected_ids:
			continue
		value = next(
			(
				row.get(key)
				for key in ("translation", "translated_title", "translated", "title_zh", "chinese")
				if row.get(key)
			),
			None,
		)
		if value is not None and str(value).strip():
			translations[row_id] = str(value).strip()
	return translations


def _clean_single_title_translation(content: str) -> str:
	content = _strip_outer_fence(content).strip()
	try:
		value = json.loads(content)
		if isinstance(value, str):
			return value.strip()
		if isinstance(value, dict):
			for key in ("translation", "translated_title", "translated", "title_zh", "chinese"):
				if value.get(key):
					return str(value[key]).strip()
	except (TypeError, ValueError, json.JSONDecodeError):
		pass
	return content.strip().strip("\"'")


def _strip_outer_fence(content: str) -> str:
	content = content.strip()
	if content.startswith("```"):
		content = re.sub(r"^```(?:json|markdown|md)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
	return content.strip()


def _safe_slug(value: str) -> str:
	slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
	return slug or hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def _walk_nodes(nodes: Iterable[SourceNode]):
	for node in nodes:
		yield node
		yield from _walk_nodes(node.children)


def _iter_pages(nodes: Iterable[SourceNode]):
	return (node for node in _walk_nodes(nodes) if node.kind == "page")


def _prune_empty_groups(nodes: list[SourceNode]) -> list[SourceNode]:
	result: list[SourceNode] = []
	for node in nodes:
		if node.kind == "group":
			node.children = _prune_empty_groups(node.children)
			if not node.children:
				continue
		result.append(node)
	return result


def _filter_tree_to_routes(nodes: list[SourceNode], routes: set[str]) -> list[SourceNode]:
	filtered: list[SourceNode] = []
	for node in nodes:
		if node.kind == "page":
			if node.source_route in routes:
				filtered.append(node)
			continue
		children = _filter_tree_to_routes(node.children, routes)
		if children:
			filtered.append(SourceNode(node.title, node.kind, node.source_route, children, node.identity))
	return filtered


def _normalize_products(products: list[str] | str | None) -> list[str]:
	if products is None:
		return list(PRODUCTS)
	if isinstance(products, str):
		products = [part.strip() for part in products.split(",") if part.strip()]
	unknown = [slug for slug in products if slug not in PRODUCTS]
	if unknown:
		raise ValueError(f"Unknown Frappe documentation products: {', '.join(unknown)}")
	return list(dict.fromkeys(products))


def _write_progress(results: dict[str, Any]) -> None:
	try:
		import frappe
		from filelock import FileLock

		path = Path(frappe.get_site_path("private", "files", "frappe-docs-zh-progress.json"))
		path.parent.mkdir(parents=True, exist_ok=True)
		with FileLock(f"{path}.lock", timeout=30):
			current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
			current.update(results)
			temporary = path.with_suffix(f"{path.suffix}.tmp")
			temporary.write_text(
				json.dumps(current, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
			)
			temporary.replace(path)
	except Exception:
		return
