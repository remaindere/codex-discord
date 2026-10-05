import os
import sys
from pathlib import Path

from ddgs import DDGS
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv(Path(__file__).with_name(".env"))


def print_results(results: list[dict]) -> bool:
    if not results:
        return False
    for index, result in enumerate(results, 1):
        print(
            f"[{index}] {result.get('title', '')}\n"
            f"URL: {result.get('url', '')}\n"
            f"Snippet: {result.get('content', '')}\n"
        )
    return True


def search_tavily(query: str, max_results: int = 5) -> bool:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY가 설정되지 않았습니다.")
    response = TavilyClient(api_key=api_key).search(
        query=query,
        search_depth="basic",
        max_results=max_results,
        include_answer=False,
        include_raw_content=False,
    )
    return print_results(response.get("results", []))


def search_ddg(query: str, max_results: int = 5) -> bool:
    return print_results(
        [
            {
                "title": item.get("title", ""),
                "url": item.get("href", ""),
                "content": item.get("body", ""),
            }
            for item in DDGS().text(query, max_results=max_results)
        ]
    )


def search(query: str) -> int:
    try:
        if search_tavily(query):
            return 0
    except Exception as error:
        print(f"Tavily 검색 실패: {error}", file=sys.stderr)
    try:
        if search_ddg(query):
            return 0
    except Exception as error:
        print(f"DDG 검색 실패: {error}", file=sys.stderr)
    print("검색 결과가 없습니다.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python web_search.py "<query>"', file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(search(" ".join(sys.argv[1:])))
