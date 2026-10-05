#!/usr/bin/env bash
#
# 클라이언트 설치 — 어느 머신·어느 사용자명에서도 그대로 동작한다.
# 스크립트가 자기 위치를 스스로 찾아 절대경로를 채우므로 경로를 손으로 고칠 필요가 없다.
#
#   bash install.sh
#
# 하는 일:
#   1. 전제 확인 — 툴 존재 · Codex 버전 · 자격증명 파일 권한
#   2. ~/.codex/config.toml 작성
#   3. ~/.aws/config 에 [profile codex-bedrock] 등록 (멱등)
#   4. credential_process 단독 확인 → Codex 실제 호출로 검증
#
# 기존 파일은 덮어쓰기 전에 .bak-<타임스탬프> 로 백업한다.
# 인증은 역할 assume 기반 단기 SigV4 자격증명 하나로만 한다 (bearer 방식 미지원).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="$HERE/codex-bedrock-credprocess.sh"
PROJECT="${MANTLE_PROJECT:-proj_3jqmm4vzcktc6vhhp4e6}"
REGION="${AWS_REGION:-us-east-1}"
MODEL="${MANTLE_MODEL_ID:-openai.gpt-5.6-sol}"
PROFILE_NAME="${PROFILE_NAME:-codex-bedrock}"
KEY_FILE="${BOOTSTRAP_KEY_FILE:-$HOME/.aws/bedrock-lab-bootstrap-key.json}"
STAMP="$(date +%Y%m%d-%H%M%S)"

say()  { printf '==> %s\n' "$1"; }
warn() { printf '  ! %s\n' "$1" >&2; }
die()  { printf '거부: %s\n' "$1" >&2; exit 1; }

# ---------- 0. 전제 확인 ----------
say "전제 확인"
for c in aws python3 codex; do
  command -v "$c" >/dev/null 2>&1 || die "$c 가 PATH 에 없다"
done
[ -f "$HELPER" ] || die "헬퍼가 없다: $HELPER"

CODEX_VER="$(codex --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n 1)"
printf '  codex %s · aws %s · python %s\n' \
  "${CODEX_VER:-unknown}" \
  "$(aws --version 2>&1 | grep -oE 'aws-cli/[0-9.]+' | cut -d/ -f2)" \
  "$(python3 -c 'import sys;print(".".join(map(str,sys.version_info[:3])))')"

if [ -n "$CODEX_VER" ]; then
  python3 - "$CODEX_VER" <<'PY' || die "Codex 0.128.0 이상이 필요하다 (bedrock provider 지원 시작 버전)"
import sys
cur = tuple(int(x) for x in sys.argv[1].split('.'))
sys.exit(0 if cur >= (0, 128, 0) else 1)
PY
fi

[ -f "$KEY_FILE" ] || die "자격증명 파일이 없다: $KEY_FILE
  다른 머신에서 안전한 경로로 옮겨온 뒤 다시 실행하십시오."

PERM="$(stat -f '%OLp' "$KEY_FILE" 2>/dev/null || stat -c '%a' "$KEY_FILE" 2>/dev/null || echo '?')"
if [ "$PERM" != "600" ]; then
  warn "자격증명 파일 권한이 $PERM 이다. 600 으로 조정한다."
  chmod 600 "$KEY_FILE"
fi

if [ -n "${AWS_BEARER_TOKEN_BEDROCK:-}" ]; then
  warn "AWS_BEARER_TOKEN_BEDROCK 이 설정돼 있다."
  warn "Codex 는 이 값을 profile 보다 먼저 쓰므로 설치 후에도 무시된다."
  warn "unset 하거나 SHELL_GUARD=1 로 재실행해 셸 가드를 설치하십시오."
fi

# ---------- 1. ~/.codex/config.toml ----------
say "~/.codex/config.toml 작성"
mkdir -p "$HOME/.codex"
CT="$HOME/.codex/config.toml"
[ -f "$CT" ] && { cp "$CT" "$CT.bak-$STAMP"; printf '  백업: %s\n' "$CT.bak-$STAMP"; }

cat > "$CT" <<TOML
model = "$MODEL"
model_provider = "amazon-bedrock"

[model_providers.amazon-bedrock]
# 필수: 없으면 요청이 project/default 로 귀속돼 401 access_denied.
# OPENAI_PROJECT 환경변수는 이 provider 에서 무시된다.
http_headers = { "OpenAI-Project" = "$PROJECT" }

[model_providers.amazon-bedrock.aws]
region = "$REGION"
profile = "$PROFILE_NAME"
TOML
printf '  모델 %s · 프로젝트 %s\n' "$MODEL" "$PROJECT"

# ---------- 2. ~/.aws/config ----------
say "~/.aws/config 에 [profile $PROFILE_NAME] 등록"
[ -x "$HELPER" ] || chmod +x "$HELPER"
mkdir -p "$HOME/.aws"
AC="$HOME/.aws/config"
[ -f "$AC" ] || : > "$AC"
cp "$AC" "$AC.bak-$STAMP"
printf '  백업: %s\n' "$AC.bak-$STAMP"

PROFILE_NAME="$PROFILE_NAME" HELPER="$HELPER" REGION="$REGION" AC="$AC" python3 <<'PY'
import os, re

name   = os.environ['PROFILE_NAME']
helper = os.environ['HELPER']
region = os.environ['REGION']
path   = os.environ['AC']

block = (
    f"[profile {name}]\n"
    f"region = {region}\n"
    f"credential_process = {helper}\n"
)

text = open(path, encoding='utf-8').read()
header = re.compile(rf'^\[profile\s+{re.escape(name)}\]\s*$', re.M)
m = header.search(text)

if m:
    # 다음 섹션 헤더까지를 이 프로파일 블록으로 보고 통째로 교체
    nxt = re.compile(r'^\[', re.M).search(text, m.end())
    end = nxt.start() if nxt else len(text)
    text = text[:m.start()] + block + text[end:]
    action = 'replaced'
else:
    if text and not text.endswith('\n'):
        text += '\n'
    if text:
        text += '\n'
    text += block
    action = 'appended'

open(path, 'w', encoding='utf-8').write(text)
print(f'  프로파일 {action}: credential_process = {helper}')
PY

# ---------- 3. 셸 가드 (opt-in) ----------
# Codex 인증 우선순위(AWS_BEARER_TOKEN_BEDROCK → SDK 체인)는 바꿀 수 없다.
# 대신 codex 를 실행하는 순간 그 변수를 벗겨내는 셸 함수를 깔아 근본적으로 막는다.
# 현재 셸의 변수는 건드리지 않고 자식 프로세스에서만 제거한다.
GUARD_MARK='# bedrock-lab codex guard'
GUARD_BODY='codex() { env -u AWS_BEARER_TOKEN_BEDROCK command codex "$@"; }'

if [ "${SHELL_GUARD:-0}" = "1" ]; then
  say "셸 가드 설치"
  case "${SHELL##*/}" in
    zsh)  RC="$HOME/.zshrc" ;;
    bash) RC="$HOME/.bashrc" ;;
    *)    RC="${SHELL_RC:-}" ;;
  esac
  if [ -z "$RC" ]; then
    warn "셸을 판별할 수 없다. SHELL_RC=<경로> 로 지정하십시오. 건너뜀."
  elif grep -qF "$GUARD_MARK" "$RC" 2>/dev/null; then
    printf '  이미 설치돼 있다: %s\n' "$RC"
  else
    cp "$RC" "$RC.bak-$STAMP" 2>/dev/null || true
    {
      printf '\n%s\n' "$GUARD_MARK"
      printf '%s\n' "$GUARD_BODY"
    } >> "$RC"
    printf '  추가: %s (백업 %s)\n' "$RC" "$RC.bak-$STAMP"
    printf '  새 셸을 열거나 `source %s` 후 적용된다.\n' "$RC"
  fi
else
  printf '  (셸 가드 미설치 — SHELL_GUARD=1 로 재실행하면 아래 한 줄을 rc 에 추가한다)\n'
  printf '    %s\n' "$GUARD_BODY"
fi

# ---------- 4. 검증 ----------
say "검증"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

printf '  credential_process 단독 확인 ... '
if bash "$HELPER" > "$WORK/c.json" 2>"$WORK/c.err"; then
  python3 -c "
import json
d = json.load(open('$WORK/c.json'))
print('ok — %s… 만료 %s' % (d['AccessKeyId'][:9], d['Expiration']))
"
else
  printf '실패\n'
  sed 's/^/    /' "$WORK/c.err" | head -n 5
  die "역할을 assume 할 수 없다.
  계정에 BedrockMantleCodexInference 역할이 있고 bootstrap 사용자에
  AssumeCodexInferenceRole 인라인 정책이 붙어 있는지 확인하십시오."
fi

printf '  Codex 호출 ... '
OUT=$(env -u AWS_BEARER_TOKEN_BEDROCK -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY \
          -u AWS_SESSION_TOKEN -u AWS_PROFILE -u OPENAI_API_KEY \
      codex exec --skip-git-repo-check -s read-only "reply with exactly: PING" 2>&1)

if printf '%s' "$OUT" | grep -qx 'PING'; then
  printf 'ok — PING\n'
else
  printf '실패\n'
  printf '%s\n' "$OUT" | grep -E '^ERROR' | head -n 2 | sed 's/^/    /'
  die "호출이 실패했다. RUNBOOK-codex.md 트러블슈팅 참조."
fi

printf '\n설치 완료. 이제 그냥 codex 를 실행하면 된다.\n'
printf 'AWS_BEARER_TOKEN_BEDROCK 은 설정하지 마십시오 — 설정하면 profile 이 무시된다.\n'
