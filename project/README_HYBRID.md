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
- `ORACLE_FORCE_THICK_MODE` (기본: `true`)
- `ORACLE_CLIENT_LIB_DIR` (기본: `C:\instantclient`, 사내 환경용)

기타:
- `QUERY_DIR` (기본: `project/query_registry/queries`)
- `APP_TIMEZONE` (기본: `Asia/Seoul`)
- `ENABLE_CONVERSATION_MEMORY` (기본: `true`)
- `MEMORY_ONLY_SINGLE` (기본: `true`)
- `MEMORY_MAX_TURNS` (기본: `4`)
- `MEMORY_MAX_CHARS_PER_MESSAGE` (기본: `300`)
- `MEMORY_DB_PATH` (미설정 시 `gocllm_memory.db`)

## 3) 쿼리 카탈로그 검증
```bash
python project/scripts/validate_queries.py
```

## 4) API 서버 실행
패키지 설치:
```bash
pip install -r project/requirements.txt
```

서버 실행:
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
- 기본 정책: `SINGLE(1:1)` + 권한 사용자(`LLM_ALLOWED_USERS_SQL`)만 LLM 응답
- `LLM_ONLY_SINGLE_CHAT=false`로 설정하면 그룹 트리거(멘션/접두어) 확장 가능
- 1:1 대화는 최근 메모리를 저장/재사용하며, `/reset`으로 초기화 가능
- 챗봇 LLM 처리 기본값은 백그라운드 큐(`LLM_WORKERS`, `LLM_JOB_QUEUE_MAX`, `LLM_MAX_CONCURRENT`)로 동작
- `ENABLE_RECALL=true` 시 "검색 중" 안내 메시지를 완료 시 회수(recall) 시도
- 이슈 라우팅 명령:
  - `/issue` (등록 폼)
  - `/issue list` 또는 `/issues` (OPEN 목록)

## 5) 테스트
```bash
pytest -q project/tests
```

## 6) 운영 보안 원칙
- Planner는 Plan JSON만 생성
- Executor는 허용 tool만 실행
- `db.query`는 registry의 `query_id` 화이트리스트만 허용
- SQL 바인딩 파라미터만 사용

## 7) 기간 질문 지원
- 기간형 질의 지원 예:
  - `올해 매출 합계`
  - `작년 FAB TG`
  - `2025년 2월~4월 판매`
  - `202501~202503 매출`
- planner가 `from_yyyymm`, `to_yyyymm`를 추출해 기간 쿼리(`psi_sales_by_period`, `psi_fab_tg_by_period`)로 라우팅합니다.
