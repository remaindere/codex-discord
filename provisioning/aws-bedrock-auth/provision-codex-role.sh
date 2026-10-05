#!/usr/bin/env bash
#
# Mode B 전제 조건 1회 생성 — bedrock-mantle 추론 권한을 가진 assume 가능 역할.
#
# 하는 일 (계정 146319282144, IAM 쓰기):
#   1. 역할 BedrockMantleCodexInference 생성 — bedrock-app-bootstrap 사용자만 assume 가능
#   2. 기존 관리형 정책 BedrockMantleSolInference 를 역할에 부착 (정책 신규 생성 없음)
#
# 이 스크립트는 IAM 을 변경한다. 실행 전 반드시 내용을 읽고,
# 관리자 자격증명(IAM-managing 상당)이 이 계정에 있는지 확인할 것.
# 확인 없이는 돌지 않도록 CONFIRM 게이트를 뒀다.
#
#   CONFIRM=yes AWS_PROFILE=<admin-profile-for-146319282144> bash provision-codex-role.sh

set -euo pipefail

ACCT=146319282144
ROLE=BedrockMantleCodexInference
POLICY_ARN="arn:aws:iam::${ACCT}:policy/BedrockMantleSolInference"
BOOTSTRAP_USER_ARN="arn:aws:iam::${ACCT}:user/bedrock-app-bootstrap"
export AWS_REGION="${AWS_REGION:-us-east-1}"

if [ "${CONFIRM:-}" != "yes" ]; then
  cat >&2 <<MSG
거부: CONFIRM=yes 가 필요하다.

이 스크립트는 계정 ${ACCT} 에서 다음을 수행한다:
  - IAM 역할 ${ROLE} 생성 (${BOOTSTRAP_USER_ARN} 만 assume 가능)
  - 정책 ${POLICY_ARN} 부착

계정 확인:
  aws sts get-caller-identity
MSG
  exit 1
fi

CALLER_ACCT=$(aws sts get-caller-identity --query Account --output text)
if [ "$CALLER_ACCT" != "$ACCT" ]; then
  printf '거부: 현재 자격증명 계정이 %s 다. %s 여야 한다.\n' "$CALLER_ACCT" "$ACCT" >&2
  exit 1
fi

TRUST=$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BootstrapUserMayAssume",
      "Effect": "Allow",
      "Principal": { "AWS": "${BOOTSTRAP_USER_ARN}" },
      "Action": "sts:AssumeRole"
    }
  ]
}
JSON
)

printf '==> 역할 생성\n'
aws iam create-role \
  --role-name "$ROLE" \
  --assume-role-policy-document "$TRUST" \
  --max-session-duration 3600 \
  --description "Short-lived SigV4 credentials for Codex CLI against bedrock-mantle" \
  --query 'Role.Arn' --output text

printf '==> 정책 부착\n'
aws iam attach-role-policy --role-name "$ROLE" --policy-arn "$POLICY_ARN"

printf '==> bootstrap 사용자에게 이 역할만 assume 하도록 인라인 권한 부여\n'
aws iam put-user-policy \
  --user-name bedrock-app-bootstrap \
  --policy-name AssumeCodexInferenceRole \
  --policy-document "$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumeCodexRoleOnly",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::${ACCT}:role/${ROLE}"
    }
  ]
}
JSON
)"

printf '\n완료. 검증:\n'
printf '  CODEX_ROLE_ARN=arn:aws:iam::%s:role/%s bash codex-bedrock-credprocess.sh | head -c 80\n' "$ACCT" "$ROLE"
