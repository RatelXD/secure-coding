# secure-coding

Django 기반 시큐어 코딩 중고거래 플랫폼과 추적 가능한 Living Report 저장소입니다.

> **현재 상태: G1 BLOCK.** 독립 GitHub 검토자가 없고 `main` 보호가 아직 활성화되지 않았으며, 결정적 PDF renderer receipt가 미완료입니다. 승인된 계약에 따라 제품 구현은 시작하지 않았습니다.

## 과제 원문 정정

원본 PDF 물리 35쪽의 `24page` 참조는 **물리 25쪽**을 뜻합니다. 근거·인용·해시는 [public source ledger](docs/report/source-ledger.md)에 있고, 절대 workstation 경로는 공개하지 않습니다.

## Report

- [Living Report](docs/report/index.md)
- [Source ledger](docs/report/source-ledger.md)
- [Evidence policy](docs/report/evidence-policy.md)
- [Verification log](docs/report/verification-log.md)
- Published Pages: <https://ratelxd.github.io/secure-coding/>

## 실행 상태

애플리케이션 실행 방법은 G1 통과 후 platform skeleton과 함께 추가합니다. 현재 checkout에는 실행 가능한 제품을 가장하는 stub이나 fallback이 없습니다.

## Release contract

G1→G2→G3→G4→실제 C1 유지보수 PATCH G5→G6→G7→G7R→G7M→G8a 순서를 지킵니다. G8a가 exact RC SHA에서 generic PDF와 public package를 통과한 뒤에만 같은 SHA를 formal/Latest로 승격합니다. identity filename과 LMS 제출은 사용자 전용 G8b이며 Team은 접근하지 않습니다.
