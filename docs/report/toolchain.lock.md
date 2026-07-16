# 선택적 PDF 작성 보조 도구

최종 제출 PDF는 사용자가 Markdown 문서를 바탕으로 직접 편집합니다. 저장소에 이미 구현된 Markdown·Mermaid 렌더링 도구는 필요할 때 초안을 확인하는 선택적 보조 수단이며, 제품 구현이나 테스트 완료 조건이 아닙니다.

## 포함된 도구

| 구성 요소 | 기록된 버전 | 용도 |
|---|---:|---|
| Pandoc | 3.6.4 | Markdown 변환 |
| WeasyPrint | 66.0 | PDF 렌더링 |
| Mermaid CLI | 11.4.2 | 다이어그램을 local 환경에서 렌더링 |
| Noto Sans CJK KR | 2.004 | 한국어 본문 글꼴 |
| Noto Sans Mono CJK KR | 2.004 | 한국어 고정폭 글꼴 |
| qpdf | 12.0.0 | PDF 구조 점검 |
| Poppler 도구 | 24.02.0 | 글꼴·링크·페이지·텍스트 점검 |

도구를 사용할 경우 네트워크를 끄고 공개 문서만 입력으로 전달하며, 비밀값·개인정보·로컬 경로가 결과에 포함되지 않는지 확인합니다. 최종 PDF는 사용자가 직접 열어 표, Mermaid, 글꼴, 링크, 페이지 잘림을 점검합니다.

<!--
Machine-readable compatibility contract for the optional helper tests. This comment is not report body text.
**Status:** OPTIONAL
Generated PDF output, renderer publication, OCI attestations, and renderer receipts are not required for assignment report completion
PDF generation, image publication, repository digests, inventory receipts, and repeat renders are optional helper outputs
## Optional published-image format
No image publication is required or currently configured.
No repository workflow publishes this optional utility and no package permission or attestation is required.
-->
