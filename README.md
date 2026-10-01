# Fast Verify Lab

빠른 모델의 초안을 먼저 보여 주고 추론 모델이 검토하는 구조를 실험한다. Python 3.10 이상과 표준 라이브러리로 실행한다.

## 터미널 UI

```sh
python3 tui.py
# API 호출 없이 화면과 실행 흐름 확인
python3 tui.py --provider mock
```

기본 제공자는 `codex`, 기본 방식은 `parallel`이다. 실행하면 빈 프롬프트 입력창을 보여 준다. 질문을 입력하고 Enter를 누르면 바로 실행한다. 결과 화면에서 `n`을 누르면 새 질문을 입력할 수 있다. mock은 고정 사례 선택 화면으로 시작한다. ChatGPT로 로그인한 Codex CLI를 사용한다. 화면에서 질문·초안·최종 답·검토 상태·시간·토큰 사용량을 확인한다. 모델 응답에 터미널 제어 문자가 있으면 표시 전에 제거한다.

| 키 | 동작 |
|---|---|
| Enter | 현재 질문 실행 |
| ↑ / ↓ | 고정 실험 사례 선택 |
| n | 새 프롬프트 입력 |
| e | 현재 질문 편집, Enter로 실행, Esc로 취소 |
| Ctrl+U | 편집 중 질문 전체 비우기 |
| r | 직접 입력한 질문에서 고정 사례로 복귀 |
| p | codex / mock / openai 제공자 전환 |
| m | fast / strong / sequential / parallel 방식 전환 |
| PgUp / PgDn | 결과 스크롤 |
| x | 진행 중인 실행 취소 |
| q | 종료, 실행 중이면 취소 요청 |

직접 입력한 질문은 codex 또는 openai로 실행한다. mock은 고정 사례만 지원한다. 실행 중에는 선택 값을 고정하고 스크롤과 취소·종료만 허용한다. 결과는 `results/ui-<UTC 시간>.json`에 저장하며 질문과 답변도 포함한다. 직접 입력한 질문은 정답 채점을 하지 않는다. 취소 결과에서는 보존한 초안을 검토 완료 답변으로 취급하지 않는다.

40열 × 12행 이상의 대화형 터미널과 Python의 curses 지원이 필요하다. macOS·Linux에서 실행한다. 창 크기에 맞춰 한글을 줄바꿈한다. OpenAI HTTP 경로는 취소 후에도 호출별 타임아웃까지 요청이 남을 수 있으며, Codex 경로는 취소 시 CLI 프로세스를 종료한다.

## 바로 실행

```sh
python3 lab.py demo
python3 lab.py bench --repeats 3
python3 -m unittest discover -s tests -v
```

기본 실행은 **mock**이다. 의도적으로 틀린 답과 잘못된 수정 사례를 넣은 고정 응답으로 실행 흐름을 확인한다. mock 정확도·시간은 실제 모델 성능을 나타내지 않는다.

`demo`는 초안 이벤트를 즉시 출력한 뒤 최종 검토 이벤트를 출력한다. 토큰 스트리밍은 구현하지 않았다. `first_answer_ms`는 완성된 초안을 사용자에게 내보낸 시점이며 첫 토큰 시간과 다르다.

## 비교하는 네 가지 방식

| mode | 실행 | API 호출 수 |
|---|---|---:|
| fast | 빠른 모델 단독 | 1 |
| strong | 추론 모델 단독 | 1 |
| sequential | 빠른 초안 → 추론 모델 검토 | 2 |
| parallel | 빠른 초안 ∥ 추론 모델 독립 풀이 → 추론 모델 비교·검토 | 3 |

병렬 방식은 초안과 독립 풀이를 함께 시작한다. 초안이 끝나면 독립 풀이가 끝나기 전에도 사용자에게 보여 준다. 두 답이 도착하면 추론 모델이 검토한다. 독립 풀이에는 초안이 들어가지 않는다. 두 답의 일치만으로 검토를 생략하지 않는다.

순차 방식의 확정 시간은 대략 `초안 시간 + 검토 시간`, 병렬 방식은 `max(초안 시간, 독립 풀이 시간) + 검토 시간`이다. 추가 호출 때문에 병렬 방식의 최종 확정이 더 늦어질 수도 있다. 두 모델을 함께 시작해도 빠른 초안 자체의 오류 검토는 초안이 나온 후 시작한다.

## ChatGPT OAuth로 실행

```sh
codex login
codex login status
python3 lab.py demo --provider codex
python3 lab.py bench --provider codex --repeats 1
```

이미 ChatGPT로 로그인한 Codex CLI가 있으면 API 키 없이 실행한다. `config.codex.json`은 빠른 역할에 `gpt-6-luna` / low / fast, 검토 역할에 `gpt-6.1-sol` / high / standard를 지정한다. `gpt-6-luna-light`와 `gpt-6.1-sol-high`는 표시용 이름이며, 모델 ID와 추론 수준을 따로 전달한다. fast는 priority, standard는 default로 요청한다. 계정에서 사용할 수 있는 모델로 설정을 바꿀 수 있다. 다른 설정은 `--config <파일>`로 지정한다.

프로그램은 공식 `codex exec --json`을 호출하고 저장된 로그인을 재사용한다. OAuth 토큰을 직접 읽거나 복사하지 않는다. `forced_login_method=chatgpt`를 지정하고 API 키 환경 변수를 자식 프로세스에서 제거한다. 로그인 상태가 맞지 않으면 실패한다. 사용량은 ChatGPT/Codex 구독 한도에 반영되며 API 데이터 공유 무료 토큰과 별개다.

각 호출은 빈 임시 작업 폴더, read-only sandbox, ephemeral 세션, 사용자 설정 미적용으로 실행한다. 프로젝트 문서를 읽는 크기를 0으로 지정한다. 정답과 mock 응답을 프롬프트에 넣지 않는다. 도구를 사용하지 않도록 지시하고, 기록에서 명령 실행·파일 변경·MCP·검색 호출을 발견하면 비교에서 실패로 처리한다. 이 검사는 실행 후 확인이므로 도구 자체를 완전히 차단하는 기능은 아니다.

검토 출력에는 JSON Schema를 적용한다. CLI가 출력한 입력·캐시 입력·출력 토큰을 저장한다. CLI 이벤트에 실제 반환 모델 ID나 서비스 티어가 없으면 이를 추측하지 않는다. `requested_model`은 요청한 모델이며 `model`은 null이다. `requested_service_tier`는 설정한 속도 등급이다. CLI가 실제 반환 티어를 제공하지 않으면 `service_tier`는 null로 기록한다. 구독 사용량을 USD로 환산하지 않으므로 비용도 null이다. CLI 시작과 로그인 처리 시간을 응답 시간에 포함한다. API의 `max_output_tokens` 설정은 Codex 실행 경로에 적용하지 않는다.

공식 문서: [Codex 인증](https://learn.chatgpt.com/docs/auth), [비대화형 실행](https://learn.chatgpt.com/docs/noninteractive).

## 실제 API 실행

```sh
cp config.example.json config.local.json
# config.local.json의 fast.model과 strong.model을 사용 가능한 모델 ID로 바꾼다.
# 지원되는 reasoning_effort를 지정한다. 지원하지 않는 모델은 null로 둔다.
# OPENAI_API_KEY는 환경 변수로 설정한다. 프로그램은 .env를 자동으로 읽지 않는다.
python3 lab.py demo --provider openai --config config.local.json
python3 lab.py bench --provider openai --config config.local.json --repeats 5
```

OpenAI Responses API를 사용한다. API 키는 파일이나 결과에 기록하지 않는다. 타임아웃은 호출별 제한이며 전체 실행 제한이 아니다. 자동 재시도는 지연 시간 측정을 왜곡하므로 넣지 않았다. 진행 중인 HTTP 요청은 비동기 작업을 취소해도 호출별 타임아웃까지 남을 수 있다. 이때 비용을 알 수 없어 null로 기록한다. 실패한 실행도 비교 결과에 남는다. SDK·외부 패키지 설치가 필요 없다.

단가를 알고 있으면 설정의 입력·캐시 입력·출력 100만 토큰당 USD를 채운다. 단가 또는 사용량이 없으면 비용을 `null`로 남긴다. 비용은 기록된 토큰과 입력한 단가로 계산한 추정치이며 청구 금액과 다를 수 있다. 추론 토큰은 API의 출력 토큰 사용량에 포함된다. 모델·응답 ID·실제 서비스 티어·사용량·각 호출 시간이 결과에 남는다.

공식 API 문서: [Responses 생성](https://developers.openai.com/api/reference/resources/responses/methods/create), [텍스트 생성](https://developers.openai.com/api/docs/guides/text).

## 결과와 판정

`bench`는 동일한 사례를 네 방식으로 실행한다. 실행 순서는 seed로 섞고 반복 번호를 기록한다. 사례를 동시에 돌리지 않아 사례 간 자체 부하를 줄인다. 병렬 방식 안의 두 호출은 동시에 실행한다.

각 실행은 새 `results/<UTC 시간>-<임의 ID>/` 폴더에 저장한다.

- `manifest.json`: 제공자, 설정, seed, 반복 수, 입력 사례
- `runs.jsonl`: 초안·최종 답, 이벤트, 호출별 시간·사용량·비용, 정답 비교
- `summary.json`: 방식별 정확도, 수정 성공 수, 잘못 수정한 수, 실패 수, 확인 불가 수, 응답 시간 중앙값, 총 추정 비용

정답은 모델에 보내지 않고 평가 단계에서만 사용한다. 시작 데이터는 계산·주어진 자료 비교·정보 부족 판정의 6개 사례다. 출력 형식을 지정한 뒤 앞뒤 공백을 제외한 완전 일치로 채점한다. 코드·장문·최신 사실 평가에는 별도 테스트나 출처 검증기를 추가해야 한다.

`accepted`는 검토 모델이 초안을 유지했다는 뜻이다. 외부 도구로 증명한 사실을 뜻하지 않는다. `corrected`는 모델이 답을 수정했다는 뜻이며 수정 후 정답 여부는 따로 채점한다. `uncertain`은 모델이 확인을 끝내지 못했다는 뜻이다. 검토 실패·잘못된 JSON·미완성 API 응답은 `verification_failed`로 기록하고 초안을 보존한다. 실패한 초안을 최종 답으로 사용하는 정책은 이 실험에 포함하지 않는다.

`regression` 사례는 정답 초안을 검토 모델이 틀리게 바꾸는 상황을 mock으로 재현한다. 정확도와 함께 이 지표를 봐야 검토의 부작용을 확인할 수 있다. 실패 시 보존한 초안이 정답일 수 있으므로 정확도와 실패 수도 함께 봐야 한다.

## 실제 실행 기록

[Codex OAuth 초기 실험](examples/codex-report.md)에 24건 비교 결과와 별도 오답 수정 시험을 기록했다. 수학적 정답과 출력 형식 일치를 구분해 해석한다.

## 실험 범위

이 저장소는 orchestration과 측정용 CLI다. 웹 UI·웹 검색·도구 실행·실제 행동 승인 기능은 포함하지 않았다. 두 모델 모두 같은 오류를 낼 수 있다. 실제 모델 비교는 대표 질문을 더 모으고 같은 모델 설정·출력 예산·자료로 반복 실행해야 한다. 초안을 보고 사용자가 행동하기까지의 시간도 별도로 측정할 필요가 있다.

API 경로와 Codex OAuth 경로는 별도로 검증한다. 실제 실험 결과는 examples와 results 폴더의 제공자 표시를 확인한다. 기본 mock 실행의 수치를 실제 모델 결과로 해석하지 않는다.
