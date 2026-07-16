# secure-coding

Django 기반 시큐어 코딩 중고거래 플랫폼과 추적 가능한 Living Report 저장소입니다.

> **현재 상태: G1 완료.** GitHub 거버넌스와 credential 폐기 검증을 마쳤습니다. 보고서 PDF 처리는 사용자가 수동으로 수행하며 G1/G8a gate가 아닙니다. 저장소의 offline renderer는 선택적 helper일 뿐 제품 작업이나 release를 차단하지 않습니다.

## Report

- [Living Report](docs/report/index.md)
- [Source ledger](docs/report/source-ledger.md)
- [Evidence policy](docs/report/evidence-policy.md)
- [Verification log](docs/report/verification-log.md)
- Published Pages: <https://ratelxd.github.io/secure-coding/>

## 실행 상태

애플리케이션 실행 방법은 이후 별도 승인된 platform skeleton과 함께 추가합니다. 현재 checkout에는 실행 가능한 제품을 가장하는 stub이나 fallback이 없습니다.

## Release contract

G1→G2→G3→G4→실제 C1 유지보수 PATCH G5→G6→G7→G7R→G7M→G8a 순서를 지킵니다. 보고서 PDF 처리는 사용자 수동 작업이며 renderer image, digest, generated PDF receipt는 G1/G8a 승격 조건이 아닙니다. identity filename과 LMS 제출은 사용자 전용 G8b이며 Team은 접근하지 않습니다.
