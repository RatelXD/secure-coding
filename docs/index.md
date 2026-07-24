# Tiny Second-hand Shopping Platform 시큐어 코딩 과제 보고서

이 사이트는 중고 거래 플랫폼을 대상으로 수행한 요구사항 분석, 시스템 설계, 구현, 체크리스트와 테스트, 유지보수, 보안 약점 개선 과정을 정리한 한국어 과제 보고서입니다.

## 보고서 바로가기

1. [전체 보고서 목차와 현재 상태](report/index.md)
2. [요구사항 분석](report/01-requirements.md)
3. [시스템 설계](report/02-system-design.md)
4. [구현 내용](report/03-implementation.md)
5. [체크리스트와 테스트](report/04-checklist-and-testing.md)
6. [유지보수](report/05-maintenance.md)
7. [보안 약점과 개선 계획](report/06-security-improvements.md)

현재 main(`1467092302f789f802114f62d4d3dcfcf1b13be8`)에는 사용자·상품·검색·채팅·알림·거래·신고·관리·후기·회원 탈퇴와 모의 내부 잔액 이체가 구현되어 있습니다. 상품 대화는 로그인한 회원만 사용할 수 있고, 송금 화면은 정수 원화만 받으며 `100,000원`처럼 표시합니다. 기존 1차·2차 정책과 상세 경계 검증은 [2차 개발 검증 계약](report/04-checklist-and-testing.md)에서 코드 구현 상태와 실행 근거를 나누어 기록합니다. 실제 실행 결과는 [기능 추적표](report/appendix/feature-traceability.md)와 [테스트 근거](report/appendix/test-evidence.md)에서 확인할 수 있습니다.

[공개 GitHub 저장소](https://github.com/RatelXD/secure-coding)
