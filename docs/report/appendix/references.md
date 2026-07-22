# 부록 C. 참고 자료와 도구

## C.1 과제·프로젝트 자료

| 자료 | 사용 범위 | 비고 |
|---|---|---|
| 승인된 과제 요구사항 명세 | 기능 범위, 보안 조건, 개발 순서 확인 | 로컬 작업 자료이며 공개 보고서에 경로·원문 정정 이력을 싣지 않음 |
| 승인된 구현 계획 | 설계·테스트·유지보수 누락 방지 | 내부 단계명과 작업 통제 용어는 제출 본문에서 제외 |
| [ChosunUniv2026Capstone/docs](https://github.com/ChosunUniv2026Capstone/docs) | 개요·요구사항·의사결정·아키텍처·상태·보고서·부록을 분리하고 추적하는 구조 참고 | 도메인 내용, 문장, 기능은 복사하지 않음 |

## C.2 공식 기술 문서

- [Django 5.2 documentation](https://docs.djangoproject.com/en/5.2/)
- [Django security topics](https://docs.djangoproject.com/en/5.2/topics/security/)
- [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [Django Channels documentation](https://channels.readthedocs.io/)
- [PostgreSQL documentation](https://www.postgresql.org/docs/)
- [Redis documentation](https://redis.io/docs/latest/)
- [Docker Compose documentation](https://docs.docker.com/compose/)

## C.3 보안 참고 자료

- [KISA 소프트웨어 개발보안 가이드](https://www.kisa.or.kr/2060204/form?lang_type=KO&page=1&postSeq=5), 2021-12-29 공개본
- [OWASP Application Security Verification Standard](https://owasp.org/www-project-application-security-verification-standard/)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP Cross Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
- [OWASP WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html)

보안 자료는 프로젝트의 실제 입력·권한·상태 흐름과 관련된 항목만 사용합니다.

## C.4 문서 작성 도구

| 도구 | 용도 | 상태 |
|---|---|---|
| Markdown | 보고서 원본 | 사용 중 |
| Mermaid | 구성도·흐름도·상태도 | 사용 중 |
| GitHub Pages | 공개 문서 탐색 | 사용 중, 최종 링크 점검 필요 |
| 선택적 로컬 PDF 보조 도구 | Markdown·Mermaid 렌더링 보조 | 선택 사항, 사용자가 최종 PDF를 직접 편집 |

최종 제출 문서에는 실제로 사용한 도구와 버전만 남깁니다. 사용하지 않은 도구는 삭제하거나 `사용하지 않음`으로 표시합니다.
