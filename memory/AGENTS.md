# Agent Instructions

Read `WIKI_SCHEMA.md` before making changes to this wiki. `WIKI_SCHEMA.md` is the source of truth for structure, workflows, records, pages, citations, and schema evolution.

## Web Search Guidelines
실시간 정보가 필요하면 다음 명령으로 검색한다.

python ../bot/web_search.py "<검색어>"

검색이 실패하면 오류 내용을 확인하고, 확인하지 못한 실시간 정보를 추측해서 답하지 않는다.
검색 결과의 URL과 요약을 근거로 답변한다.