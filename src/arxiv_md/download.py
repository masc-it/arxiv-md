from __future__ import annotations

import argparse
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from urllib import error, parse, request

from arxiv_md.cli_output import emit_error, emit_ok

ATOM_NS = "http://www.w3.org/2005/Atom"
API_URLS = (
    "https://export.arxiv.org/api/query",
    "http://export.arxiv.org/api/query",
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

ID_RE = re.compile(
    r"^(?:arXiv:)?(?:\d{4}\.\d{4,5}|[a-z.-]+/\d{7})(?:v\d+)?$",
    re.IGNORECASE,
)


@dataclass(slots=True)
class Paper:
    arxiv_id: str
    title: str
    pdf_url: str
    abstract_url: str


def normalize_arxiv_id(value: str) -> str:
    value = value.strip()
    if value.lower().startswith("arxiv:"):
        value = value[6:]
    return value


def base_arxiv_id(value: str) -> str:
    value = normalize_arxiv_id(value)
    return re.sub(r"v\d+$", "", value, flags=re.IGNORECASE)


def exact_arxiv_id(value: str) -> str:
    return normalize_arxiv_id(value)


def is_arxiv_id(value: str) -> bool:
    return bool(ID_RE.match(value.strip()))


def fetch_feed(url: str) -> ET.Element:
    req = request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with request.urlopen(req, timeout=60) as resp:
            payload = resp.read()
    except error.HTTPError as exc:
        raise RuntimeError(f"arXiv API request failed: HTTP {exc.code}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"arXiv API request failed: {exc.reason}") from exc

    try:
        return ET.fromstring(payload)
    except ET.ParseError as exc:
        raise RuntimeError("arXiv API returned invalid XML") from exc


def text_or_empty(node: ET.Element, path: str) -> str:
    return node.findtext(path, default="", namespaces={"atom": ATOM_NS}).strip()


def paper_from_entry(entry: ET.Element) -> Paper:
    abstract_url = text_or_empty(entry, "atom:id")
    arxiv_id = (
        exact_arxiv_id(abstract_url.rsplit("/abs/", 1)[-1]) if abstract_url else ""
    )
    title = text_or_empty(entry, "atom:title")

    pdf_url = ""
    for link in entry.findall("atom:link", {"atom": ATOM_NS}):
        if (
            link.attrib.get("title") == "pdf"
            or link.attrib.get("type") == "application/pdf"
        ):
            pdf_url = link.attrib.get("href", "").strip()
            if pdf_url:
                break

    if not pdf_url and abstract_url:
        pdf_url = abstract_url.replace("/abs/", "/pdf/")

    if not arxiv_id or not pdf_url:
        raise RuntimeError("arXiv entry is missing an ID or PDF link")

    return Paper(
        arxiv_id=arxiv_id,
        title=title,
        pdf_url=pdf_url,
        abstract_url=abstract_url,
    )


def parse_feed(feed: ET.Element) -> list[Paper]:
    return [
        paper_from_entry(entry)
        for entry in feed.findall("atom:entry", {"atom": ATOM_NS})
    ]


def download_pdf(url: str, destination: Path) -> None:
    req = request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with request.urlopen(req, timeout=120) as resp, destination.open("wb") as fh:
            shutil.copyfileobj(resp, fh)
    except error.HTTPError as exc:
        raise RuntimeError(f"PDF download failed: HTTP {exc.code}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"PDF download failed: {exc.reason}") from exc


def safe_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    value = value.strip("._-")
    return value or "arxiv-paper"


def build_request_url(ids: list[str], base_url: str) -> str:
    params = {"id_list": ",".join(ids)}
    return f"{base_url}?{parse.urlencode(params, quote_via=parse.quote_plus)}"


def build_search_url(query: str, max_results: int, base_url: str) -> str:
    params = {
        "search_query": f"all:{query}",
        "max_results": str(max_results),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    return f"{base_url}?{parse.urlencode(params, quote_via=parse.quote_plus)}"


def search(query: str, max_results: int = 1) -> list[Paper]:
    last_error: Exception | None = None
    for base_url in API_URLS:
        try:
            feed = fetch_feed(build_search_url(query, max_results, base_url))
            return parse_feed(feed)
        except RuntimeError as exc:
            last_error = exc
    raise RuntimeError(str(last_error) if last_error else "arXiv search failed.")


def _emit_error(message: str, *, as_json: bool, code: str) -> int:
    if as_json:
        emit_error(message, code=code)
    else:
        print(message, file=sys.stderr)
    return 1


def _fetch_arxiv_feed(
    normalized_ids: list[str],
) -> tuple[ET.Element | None, str | None]:
    last_error: Exception | None = None
    for base_url in API_URLS:
        try:
            return fetch_feed(build_request_url(normalized_ids, base_url)), None
        except RuntimeError as exc:
            last_error = exc
    return None, str(last_error) if last_error else "arXiv API request failed."


def _download_one_paper(
    requested: str,
    paper: Paper | None,
    outdir: Path,
    *,
    as_json: bool,
    downloaded: list[dict[str, str]],
    failed: list[dict[str, str]],
) -> None:
    if paper is None:
        failed.append({"arxiv_id": requested, "error": "Missing arXiv entry"})
        if not as_json:
            print(f"Missing arXiv entry for {requested}", file=sys.stderr)
        return

    destination = outdir / f"{safe_filename(paper.arxiv_id)}.pdf"
    try:
        download_pdf(paper.pdf_url, destination)
    except RuntimeError as exc:
        failed.append({"arxiv_id": paper.arxiv_id, "error": str(exc)})
        if not as_json:
            print(f"{paper.arxiv_id}: {exc}", file=sys.stderr)
        return

    downloaded.append(
        {
            "arxiv_id": paper.arxiv_id,
            "path": str(destination),
            "source": paper.abstract_url,
        }
    )
    if not as_json:
        print(f"Downloaded: {destination}")
        print(f"Source: {paper.abstract_url}")


def _build_paper_index(
    papers: list[Paper],
) -> tuple[dict[str, Paper], dict[str, Paper]]:
    by_exact = {exact_arxiv_id(p.arxiv_id): p for p in papers}
    by_base = {base_arxiv_id(p.arxiv_id): p for p in papers}
    return by_exact, by_base


def _lookup_paper(
    requested: str,
    by_exact: dict[str, Paper],
    by_base: dict[str, Paper],
) -> Paper | None:
    return by_exact.get(exact_arxiv_id(requested)) or by_base.get(
        base_arxiv_id(requested)
    )


def run(ids: list[str], outdir: Path, *, as_json: bool = False) -> int:
    invalid = [value for value in ids if not is_arxiv_id(value)]
    if invalid:
        return _emit_error(
            "Invalid arXiv ID(s): " + ", ".join(invalid),
            as_json=as_json,
            code="invalid_input",
        )

    normalized_ids = [normalize_arxiv_id(value) for value in ids]

    feed, error_msg = _fetch_arxiv_feed(normalized_ids)
    if feed is None:
        assert error_msg is not None
        return _emit_error(error_msg, as_json=as_json, code="arxiv_api_error")

    by_exact, by_base = _build_paper_index(parse_feed(feed))
    outdir.mkdir(parents=True, exist_ok=True)

    downloaded: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []
    for requested in normalized_ids:
        paper = _lookup_paper(requested, by_exact, by_base)
        _download_one_paper(
            requested,
            paper,
            outdir,
            as_json=as_json,
            downloaded=downloaded,
            failed=failed,
        )

    if as_json:
        emit_ok({"downloaded": downloaded, "failed": failed})
    return 1 if failed else 0


def build_parser(
    parent: argparse._SubParsersAction | None = None,
) -> argparse.ArgumentParser:
    kwargs: dict = dict(description=__doc__)
    if parent is not None:
        parser = parent.add_parser("download", **kwargs)
    else:
        parser = argparse.ArgumentParser(**kwargs)
    parser.add_argument("ids", nargs="+", help="one or more arXiv IDs")
    parser.add_argument("--outdir", default="downloads", help="directory to save PDFs")
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a machine-readable JSON envelope on stdout instead of progress lines",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args.ids, Path(args.outdir), as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
