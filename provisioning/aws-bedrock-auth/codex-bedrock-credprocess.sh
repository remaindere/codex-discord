#!/usr/bin/env bash
#
# Mode B — AWS credential_process 헬퍼.
# 단기 자격증명을 stdout 에 JSON 으로 내보낸다. Codex(및 모든 AWS SDK)가 직접 호출한다.
#
# ~/.aws/config:
#   [profile codex-bedrock]
#   region = us-east-1
#   credential_process = /Users/gyuil/Documents/dev/bedrock-mantle-lab/codex/codex-bedrock-credprocess.sh
#
# ~/.codex/config.toml:
#   [model_providers.amazon-bedrock.aws]
#   region = "us-east-1"
#   profile = "codex-bedrock"
#
# 전제: CODEX_ROLE_ARN 역할에 bedrock-mantle 추론 권한이 붙어 있어야 한다.
#       (provision-codex-role.sh 로 1회 생성)
# 역할이 없으면 assume-role 이 실패하므로, 그때는 sts get-session-token 으로
# 폴백하지 않는다 — 폴백하면 401 을 권한 문제로 착각하게 된다.

set -euo pipefail

BOOTSTRAP_KEY_FILE="${BOOTSTRAP_KEY_FILE:-$HOME/.aws/bedrock-lab-bootstrap-key.json}"
ROLE_ARN="${CODEX_ROLE_ARN:-arn:aws:iam::146319282144:role/BedrockMantleCodexInference}"
SESSION_TTL="${SESSION_TTL:-3600}"
REGION="${AWS_REGION:-us-east-1}"

bk() { python3 -c "
import json
print(json.load(open('$BOOTSTRAP_KEY_FILE'))['AccessKey']['$1'])
"; }

AWS_ACCESS_KEY_ID="$(bk AccessKeyId)" \
AWS_SECRET_ACCESS_KEY="$(bk SecretAccessKey)" \
AWS_DEFAULT_REGION="$REGION" \
aws sts assume-role \
  --role-arn "$ROLE_ARN" \
  --role-session-name "codex-$(date +%s)" \
  --duration-seconds "$SESSION_TTL" \
  --output json \
| python3 -c "
import json, sys
c = json.load(sys.stdin)['Credentials']
json.dump({
    'Version': 1,
    'AccessKeyId': c['AccessKeyId'],
    'SecretAccessKey': c['SecretAccessKey'],
    'SessionToken': c['SessionToken'],
    'Expiration': c['Expiration'],
}, sys.stdout)
"
