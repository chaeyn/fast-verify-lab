# Fast Verify Lab

[English](README.md) · [사용 가이드](GUIDE.md) · [기여 가이드](CONTRIBUTING.md) · [릴리스](https://github.com/chaeyn/fast-verify-lab/releases)

빠른 모델의 답변을 먼저 확인하세요. 검토 모델은 그 답변을 검토합니다. 검토 모델이 답변을 유지하면 앱은 상태만 표시합니다. 답변을 수정하면 앱은 수정 답변을 표시합니다.

Fast Verify Lab은 터미널 앱과 모델 비교 도구입니다. 초안과 검토에 서로 다른 제공자와 모델을 지정할 수 있습니다.

```text
질문 -> 빠른 초안 -> 검토 -> accepted: 초안 유지
                         -> corrected: 수정 답변 표시
                         -> uncertain 또는 실패: 검토 상태 표시
```

두 모델이 같은 오류를 낼 수 있습니다. `accepted`는 검토 모델이 초안을 유지했다는 뜻입니다. 사실 확인을 완료했다는 뜻은 아닙니다.

## 설치

Python 3.11 이상을 사용하세요. 모의 실행에는 계정이나 API 키가 필요하지 않습니다.

### macOS, Linux, WSL

```sh
git clone https://github.com/chaeyn/fast-verify-lab.git
cd fast-verify-lab
sh install.sh
sh run.sh
```

설치 스크립트는 `.venv`를 만들거나 기존 환경을 재사용합니다. 가상 환경을 직접 활성화할 필요가 없습니다.
`sh run.sh`는 TUI를 실행합니다. 앱이 없으면 먼저 설치합니다.
모의 실행은 `sh run.sh demo`로 시작하세요.

아래 예제에서는 `fast-verify` 대신 `sh run.sh`를 사용하세요.
설정과 업데이트 방법은 [셸 스크립트 가이드](GUIDE.md#shell-installation-and-launch)를 확인하세요.

### Windows PowerShell

```powershell
git clone https://github.com/chaeyn/fast-verify-lab.git
cd fast-verify-lab
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[tui]"
.\.venv\Scripts\fast-verify.exe demo
.\.venv\Scripts\fast-verify.exe tui --provider mock
```

Windows에서는 `tui` 추가 옵션이 `windows-curses`를 설치합니다. 텍스트 CLI에는 실행용 외부 패키지가 필요하지 않습니다. 운영체제별 검증 범위는 [지원 환경](docs/support.md)에서 확인하세요.

## 모델 연결

1. 사용할 제공자의 CLI를 설치하거나 API 키를 발급받으세요.
2. `fast-verify setup`을 실행하세요.
3. Draft에서 초안 제공자를 선택하세요.
4. Review에서 검토 제공자를 선택하세요.
5. 계정에서 사용할 수 있는 모델 ID를 입력하세요.
6. `fast-verify doctor`를 실행하세요.
7. `fast-verify tui`를 실행하세요.

Windows에서 가상 환경을 활성화하지 않았다면 `fast-verify` 대신 `.\.venv\Scripts\fast-verify.exe`를 사용하세요.

| 연결 | 인증 | 설정 ID |
|---|---|---|
| Codex | Codex CLI의 ChatGPT 로그인 | `codex` |
| Claude Code | Claude Code CLI의 저장된 로그인 | `claude` |
| OpenAI API | `OPENAI_API_KEY` 환경 변수 | `openai` |
| Anthropic API | `ANTHROPIC_API_KEY` 환경 변수 | `anthropic` |
| OpenAI 호환 API | 설정에서 지정한 환경 변수 | `api` |
| 모의 응답 | 인증 없음 | `mock` |

API 키는 환경 변수에 저장하세요. 설정에는 환경 변수 이름만 입력하세요. 앱은 `.env` 파일을 자동으로 읽지 않습니다. [키 설정 절차](GUIDE.md#api-keys)를 확인하세요.

Codex는 `codex login`으로 로그인하세요. Claude Code는 `claude auth login`으로 로그인하세요. CLI 로그인과 API 키는 서로 다른 계정이나 사용 한도를 사용할 수 있습니다.

`doctor`는 설치와 인증 설정을 점검합니다. 실제 모델 응답이나 과금 상태는 확인하지 않습니다. 짧은 질문으로 연결을 확인하세요.

```sh
fast-verify ask "17 곱하기 19는? 숫자만 답하세요." --no-save
```

## TUI 사용

질문을 입력한 후 Enter를 누르세요. 기본 모드는 `sequential`입니다. 앱은 초안을 표시한 후 검토 모델을 한 번 호출합니다.

| 키 | 동작 |
|---|---|
| Enter | 질문 또는 선택한 예제 실행 |
| Ctrl+O | 줄바꿈 입력 |
| Ctrl+D | 여러 줄 질문 실행 |
| Esc | 질문 편집 종료 |
| n / e | 새 질문 입력 / 현재 질문 편집 |
| s | 편집창 밖에서 연결 설정 |
| F1 | 도움말 표시 |
| PgUp / PgDn | 결과 스크롤 |
| x | 현재 실행 취소 |
| q | 편집창 밖에서 앱 종료 |

앱은 질문과 답변을 기본으로 저장합니다. 저장을 끄려면 다음 명령을 사용하세요.

```sh
fast-verify tui --no-save
```

이 옵션은 이전 파일을 삭제하지 않습니다. 제공자의 보관 정책에도 영향을 주지 않습니다. API 요청은 취소 후에도 타임아웃까지 실행될 수 있습니다.

## 결과 해석

| 상태 | 의미 |
|---|---|
| `accepted` | 검토 모델이 초안을 유지함 |
| `corrected` | 검토 모델이 답변을 수정함 |
| `uncertain` | 검토 모델이 주요 쟁점을 해결하지 못함 |
| `verification_failed` | 초안 생성 후 검토 실패 |
| `failed` | 초안 생성 전 실행 실패 |
| `unreviewed` | 단일 모델 모드로 실행하여 검토를 하지 않음 |
| `cancelled` | 사용자가 실행을 취소함 |

검토에 실패하면 초안은 검증되지 않은 상태로 남습니다. 수정된 답변에도 오류가 있을 수 있습니다. 모의 실행의 정확도와 시간은 실제 모델 성능을 나타내지 않습니다.

## 기여와 문서

버그를 보고할 때 운영체제, Python 버전, 명령, 예상 결과, 실제 결과를 적으세요. API 키와 개인 질문은 제거하세요. [기여 가이드](CONTRIBUTING.md)에 개발 환경과 테스트 절차가 있습니다.

영어는 기본 문서 언어입니다. 이 소개 문서는 핵심 사용법을 한국어로 제공합니다. 상세 가이드는 영어로 제공합니다. 인터페이스는 영어를 사용하며, 질문과 답변은 요청한 언어를 유지합니다.

두 언어의 문서에 짧은 문장, 능동형, 단계별 지시, 일관된 용어를 적용합니다. [작성 규칙](docs/writing-style.md)은 ASD-STE100을 참고합니다. ASD-STE100은 영어 표준이며, 이 프로젝트는 공식 적합성이나 인증을 주장하지 않습니다.

이 프로젝트는 [MIT 라이선스](LICENSE)를 사용합니다.
