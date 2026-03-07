# DS ASSISTANT API – GPT OSS User Guide  

*Version: 2026‑03‑06*  

---  

## 📌 개요  

DS ASSISTANT API – GPT OSS는 **DS LLM API** 구독 서비스에 추가로 제공되는 GPT‑OSS 모델(120B) 호출 인터페이스입니다.  
본 가이드는 **신규·기존 사용자** 모두가 API 사용 신청, 인증키 발급, 호출 방법 및 샘플 코드를 한눈에 확인할 수 있도록 작성되었습니다.  

---  

## 1️⃣ 사용 신청 (STEP 1)  

| 구분 | 신청 방법 | 비고 |
|------|----------|------|
| **기존 사용자**<br/>(‘ASSISTANT API‑HCX’ 또는 ‘DS LLM API’ 구독 중) | DS ASSISTANT API Usage Application – DS Assistant – DS Confluence → **STEP 5**부터 진행 | 동일 서비스명에서만 신청 가능 |
| **신규 사용자** | DS ASSISTANT API Usage Application – DS Assistant – DS Confluence → **STEP 1**부터 진행 |  |

> **※** 기존에 ‘DS LLM API’를 구독 중이라면 별도 결재 없이 **‘GPT OSS API’ 구독 신청만** 하면 됩니다.  

---  

## 2️⃣ 테스트용 `x‑dep‑ticket` 키  

| 항목 | 내용 |
|------|------|
| **키 종류** | 공용 테스트 키 (지속적인 서비스 용도 금지) |
| **요청 제한** | **분당 30건** (초과 시 `429 Too Many Requests` 반환, IP 차단 가능) |
| **주의** | 실제 서비스 용도로 사용하지 말고, **간단한 기능 테스트**에만 활용하세요. |
| **키** | `credential:TICKET-18ab56e4-99cb-4b44-af32-9ad78449fd80:ST0000101295-STG:Bg9vvJDsTo6w23jrHq6j-Q5Itu6yJRQhOmL8VIY3GE1w:-1:Qmc5dnZKRHNUbzZ3MjNqckhxNmotUTVJdHU2eUpSUWhPbUw4VklZM0dFMXc=:signature=O05mxEkLrDAYwCVLzbiPvgMmCmkLXU3oI9eDGZ6R7otW3C5dE0zssv5_a2knr8QYScmOD0v4IvnF4h2vXe2fQ3zLiM1p6qaK6fSRw0l5FDDYSo0BeXbd_cg==` |
| **URL (예시)** | `http://apigw-stg.samsungds.net:8000/gpt-oss/1/gpt-oss-120b/v1/chat/completions` (STG) <br/>Prod 환경에서는 도메인·포트가 다릅니다. |

---  

## 3️⃣ GPT OSS API 파라미터 설명 (STEP 2)

### 3‑1️⃣ HTTP Header  

| Header | Type | 설명 |
|--------|------|------|
| **x‑dep‑ticket** | `string` | DS API HUB에서 발급받은 credential 키 |
| **User-Type** | `string` | `"AD_ID"` 로 고정 |
| **User-Id** | `string` | 사용자의 AD ID |
| **Send-System-Name** | `string` | 신청 양식에 기입한 시스템 이름 |
| **Prompt-Msg-Id** | `string` | 호출당 **UUID** (예: `str(uuid.uuid4())`) |
| **Completion-Msg-Id** | `string` | 호출당 **UUID** |
| **Content-Type** | `string` | `application/json` |
| **Accept** | `string` | `text/event-stream` → 스트리밍, 그 외 → 한 번에 반환 |

### 3‑2️⃣ HTTP Body (JSON)  

```json
{
  "messages": [
    { "role": "system",   "content": "You are a pirate chatbot who always responds in pirate speak!" },
    { "role": "user",     "content": "hello" }
  ],
  "model": "openai/gpt-oss-120b",
  "max_tokens": 500,
  "temperature": 0.3,
  "stream": true
}
```

| Field | Type | 설명 |
|-------|------|------|
| **messages** | `array` | 대화 메시지 리스트 |
| `messages.role` | `enum` | `system` / `user` / `assistant` |
| `messages.content` | `string` | 각 메시지 내용 |
| **model** | `string` | `"openai/gpt-oss-120b"` (고정) |
| **max_tokens** | `int` | 생성 최대 토큰 수 |
| **stream** | `bool` | `true` → 스트리밍, `false` → 전체 반환 |
| **temperature** | `float` | 0 ~ 1, 값이 클수록 다양성 ↑ |

---  

## 4️⃣ 호출 예시 (STEP 5)  

### 4‑1️⃣ 순수 `requests` 사용 (Python)

```python
import requests, json, uuid
from pprint import pprint

# ── 기본 설정 ──
api_base_url = 'http://apigw-stg.samsungds.net:8000/gpt-oss/1/gpt-oss-120b/v1/chat/completions'
credential_key = 'credential:TICKET-~~~'   # 실제 키 입력

payload = json.dumps({
    "model": "openai/gpt-oss-120b",
    "messages": [
        {"role": "system", "content": "You are a pirate chatbot who always responds in pirate speak!"},
        {"role": "user",   "content": "hello"}
    ],
    "temperature": 0.5,
    "stream": False
})

headers = {
    'x-dep-ticket'      : credential_key,
    'Send-System-Name'  : 'Send-System-Name 입력해주세요.',
    'User-Id'           : 'KNOX ID 입력해주세요.',
    'User-Type'         : 'AD_ID',
    'Prompt-Msg-Id'     : str(uuid.uuid4()),
    'Completion-Msg-Id': str(uuid.uuid4()),
    'Accept'            : 'text/event-stream; charset=utf-8',
    'Content-Type'      : 'application/json'
}

try:
    resp = requests.post(api_base_url, headers=headers, data=payload, timeout=None)
    resp.raise_for_status()
except Exception as e:
    print("Request error:", e)
    raise

result = resp.json()
print("### Response JSON")
pprint(result)
print("\n### Output Message")
print(result["choices"][0]["message"]["content"])
```

#### 실행 결과 (예시)

```text
### Output Message
Ahoy there, matey! Well shiver me timbers, 'tis a fine day to be havin' a chat, aye? ...
```

---  

### 4‑2️⃣ **Sliding Window API** (대화 유지)

```python
import requests, json, uuid
from pprint import pprint

api_base_url = 'http://apigw-stg.samsungds.net:8000/gpt-oss/1/gpt-oss-120b/v1/chat/completions'
sliding_url   = 'http://apigw-stg.samsungds.net:8000/gpt-oss/1/gpt-oss-120b/api/slidingwindow'
credential_key = 'credential:TICKET-~~~'

data = {
    "model": "openai/gpt-oss-120b",
    "messages": [
        {"role":"system","content":"You are a pirate chatbot who always responds in pirate speak!"},
        {"role":"user",  "content":"hello"}
    ],
    "temperature": 0.5,
    "stream": False
}
headers = {
    'x-dep-ticket'      : credential_key,
    'Send-System-Name'  : 'Send-System-Name 입력해주세요.',
    'User-Id'           : 'KNOX ID 입력해주세요.',
    'User-Type'         : 'KNOX ID 입력해주세요.',
    'Prompt-Msg-Id'     : str(uuid.uuid4()),
    'Completion-Msg-Id': str(uuid.uuid4()),
    'Accept'            : 'text/event-stream; charset=utf-8',
    'Content-Type'      : 'application/json'
}

def add_msg(role, content):
    data["messages"].append({"role": role, "content": content})
    pprint(data)

def call_llm():
    resp = requests.post(api_base_url, headers=headers, json=data)
    resp.raise_for_status()
    return resp.json()

def call_sliding_window():
    resp = requests.post(sliding_url, headers=headers, json=data)
    resp.raise_for_status()
    return resp.json()

# 예시 흐름
add_msg("user", "코루틴을 최대한 자세하게 설명하고 예제를 만들어줘")
llm_res = call_llm()
add_msg("assistant", llm_res["choices"][0]["message"]["content"])
add_msg("user", "답변을 영어로도 해줘")
llm_res = call_llm()
```

---  

### 4‑3️⃣ `openai` 파이썬 SDK 활용

```python
import uuid, os
from openai import OpenAI

os.environ["OPENAI_API_KEY"] = "dummy"   # 실제 키는 사용 안 함

api_base_url = "http://apigw-stg.samsungds.net:8000/gpt-oss/1/gpt-oss-120b/v1"
credential_key = "credential:TICKET-~~~"

client = OpenAI(
    base_url = api_base_url,
    default_headers = {
        "x-dep-ticket"      : credential_key,
        "Send-System-Name"  : "test_api_1",
        "User-Id"           : "KNOX ID 입력해주세요.",
        "User-Type"         : "AD_ID",
        "Prompt-Msg-Id"     : str(uuid.uuid4()),
        "Completion-Msg-Id": str(uuid.uuid4()),
    }
)

completion = client.chat.completions.create(
    model="openai/gpt-oss-120b",
    messages=[
        {"role":"system","content":"You are a helpful assistant."},
        {"role":"user",  "content":"How are you?"}
    ]
)

print(completion.choices[0].message.content)
```

---  

### 4‑4️⃣ `langchain` + `ChatOpenAI` 사용

```python
import os, uuid
from langchain_openai import ChatOpenAI

os.environ["OPENAI_API_KEY"] = "dummy"

api_base_url = "http://apigw-stg.samsungds.net:8000/gpt-oss/1/gpt-oss-120b/v1"
credential_key = "credential:TICKET-~~~"

llm = ChatOpenAI(
    base_url = api_base_url,
    model    = "openai/gpt-oss-120b",
    default_headers = {
        "x-dep-ticket"      : credential_key,
        "Send-System-Name"  : "test_api_1",
        "User-Id"           : "KNOX ID 입력해주세요.",
        "User-Type"         : "AD_ID",
        "Prompt-Msg-Id"     : str(uuid.uuid4()),
        "Completion-Msg-Id": str(uuid.uuid4()),
    }
)

print(llm.invoke("안녕?"))
```

---  

## 5️⃣ 주의사항 & FAQ  

| 질문 | 답변 |
|------|------|
| **키가 노출돼도 되나요?** | 테스트 키는 **공용**이며 제한된 용도로만 사용합니다. 실제 서비스에서는 각 서비스 별 **전용 credential**을 발급받아 사용하세요. |
| **스트리밍을 쓰려면 어떻게 해야 하나요?** | `stream=True` 로 요청하고 `Accept: text/event-stream` 헤더를 유지하면 서버가 SSE 형식으로 토큰을 순차 전송합니다. `requests`에서는 `iter_lines()` 로 읽을 수 있습니다. |
| **프롬프트·응답 길이 제한은?** | `max_tokens` 로 최대 생성 토큰 수를 제어합니다. 입력 토큰(프롬프트)과 출력 토큰(응답) 합이 모델 한계(≈ 120 B 토큰) 내에 있어야 합니다. |
| **프로덕션 환경 URL은?** | 프로덕션은 `apigw-prod.samsungds.net` (포트·경로 동일)이며, 별도 **Prod credential**을 사용합니다. |
| **Sliding Window API는 언제 쓰나요?** | 대화 컨텍스트를 유지하면서 **이전 대화 전체를 재전송**하지 않고, 서버에 현재 대화 흐름만 전달하고자 할 때 사용합니다. 모델별 구현 차이가 있으니 DS Confluence 문서를 참고하세요. |

---  

## 📚 참고 문서  

- **DS Assistant – GPT‑OSS User Guide** (Confluence)  
- **DS API HUB** – 인증·키 관리 가이드  
- **OpenAI API Spec** – Chat‑completion 파라미터 상세  
- **LangChain Docs** – `ChatOpenAI` 연동 예시  

---  

*본 README는 내부·외부 공유 시 **핵심 정보(엔드포인트, 헤더, 샘플 코드)**만 포함하도록 가공해 주세요.*
