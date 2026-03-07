# Hybrid RAG + DB Assistant (Planner–Executor–Synthesizer)

## 1) 개요
- 단일 질문에서 `RAG + DB`를 함께 처리합니다.
- SQL은 **Query Catalog(query_id 기반)** 만 실행합니다. (LLM SQL 생성 금지)
- 새 쿼리는 `project/query_registry/queries/*.yml` 파일 추가만으로 반영됩니다.

## 2) 실행 환경변수
필수(LLM):
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`

필수(DB):
- `ORACLE_USER`
- `ORACLE_PW` (또는 `ORACLE_PASSWORD`)
- `ORACLE_DSN` (권장)
  - 또는 `ORACLE_HOST`, `ORACLE_PORT`, `ORACLE_SERVICE`

기타:
- `QUERY_DIR` (기본: `project/query_registry/queries`)
- `APP_TIMEZONE` (기본: `Asia/Seoul`)

## 3) 쿼리 카탈로그 검증
```bash
python project/scripts/validate_queries.py
```

## 4) API 서버 실행
```bash
uvicorn project.main:app --host 0.0.0.0 --port 8010 --reload
```

Health check:
```bash
curl http://127.0.0.1:8010/health
```

질문:
```bash
curl -s -X POST http://127.0.0.1:8010/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"2월 WC 버전 판매 몇개야"}'
```

Knox 챗봇 Webhook:
- `POST /message`
- `KNOX_SYSTEM_ID`, `KNOX_TOKEN` 설정 시 startup에서 자동 연결
- LLM 트리거는 기존과 동일하게 `SINGLE 일반문장`, `/ask`, `질문:`, `GROUP 멘션/접두어` 지원

## 5) 테스트
```bash
pytest -q project/tests
```

## 6) 운영 보안 원칙
- Planner는 Plan JSON만 생성
- Executor는 허용 tool만 실행
- `db.query`는 registry의 `query_id` 화이트리스트만 허용
- SQL 바인딩 파라미터만 사용
