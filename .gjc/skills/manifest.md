# Pinned project skills

This is the immutable receipt for selected project-local skill subtrees. Installed files must match these hashes. Network rendering is prohibited: Mermaid uses local `mmdc`; Kroki, `mermaid.live`, and other rendering endpoints are disabled.

## humanize-korean

- Repository: <https://github.com/epoko77-ai/im-not-ai>
- Commit: [`14aeb52d13e737beb4e999cb7cb92275d0969689`](https://github.com/epoko77-ai/im-not-ai/commit/14aeb52d13e737beb4e999cb7cb92275d0969689)
- Selected upstream subtree: `.claude/skills/humanize-korean`
- Installed subtree: `.gjc/skills/humanize-korean`
- Non-selected alternate: `codex/skills/humanize-korean`
- License: MIT; upstream `LICENSE`; 1,067 bytes; SHA-256 `4cc7e8c439fe42f09d98457599c129ea6df9e5d0e622750d75952b441a38343f`
- Canonical subtree-manifest SHA-256: `bde426cefcd1d662b2a39cc8c3640253386d61e1e641392b9e325ddbfb717ce9`

| Installed path under `humanize-korean/` | Bytes | SHA-256 |
|---|---:|---|
| `SKILL.md` | 10,738 | `439f97ced0f0c391b602b6c6eca1286b7d670e177d6044a8df9d9c9445f582c2` |
| `references/ai-tell-taxonomy.md` | 59,962 | `b061ad516056434cd58e86961cde510d5b6c580bb8e2fc7025acee82335d904d` |
| `references/baseline.json` | 6,139 | `3880335a2b760fd505531e303ff9fff7f0725f8f2e98dc965a7808c21616d958` |
| `references/baseline_v2.json` | 13,487 | `b5f1725bd02fb4cc40eece68c5b8f1d7c7655775743196d8fd0bc5978f2ed916` |
| `references/metrics.py` | 14,550 | `a665faef60c88a045e232ac633fe19335d123a58a5dd8e493708c7c5954a5f60` |
| `references/metrics_v2.py` | 27,564 | `4551621f74f042c44bca871f372c14d2f6fce40582fe49b41b0a8d6d8dca8b98` |
| `references/quick-rules.md` | 9,144 | `ad84c6dc8136378dc4434bd90d1e68e8fdc2bb63ccbbadc9394f9e2c5d3c92ff` |
| `references/rewriting-playbook.md` | 11,443 | `2fb785cb418f79676cec80ce98a427cc4ef4dffd9fddf831fe3f7383dc8d4b58` |
| `references/scholarship.md` | 24,380 | `f496dffcce98cbd7b496eb2708e7de1a2e48035e53bedabd750e9f840c5cf246` |
| `references/web-service-spec.md` | 8,010 | `be887c5e60b9a37e63a4aa8156ada0da4298098a51451925a3a22b9a37e25f6a` |

## mermaid-skill

- Repository: <https://github.com/Agents365-ai/mermaid-skill>
- Commit: [`15d09cfff6cf940c2fc51324b57c482f36420f3b`](https://github.com/Agents365-ai/mermaid-skill/commit/15d09cfff6cf940c2fc51324b57c482f36420f3b)
- Selected upstream subtree: `skills/mermaid-skill`
- Installed subtree: `.gjc/skills/mermaid-skill`
- License: MIT; upstream `LICENSE`; 1,069 bytes; SHA-256 `0d43b46456eda48a9054fbfa915ac80e150f5db5cf90714eda710c02e1df461a`
- Canonical subtree-manifest SHA-256: `bc3a9c577521acacabf46f01cc9847f41d4b50eff90f00baf4ddbd4af27cf06b`

| Installed path under `mermaid-skill/` | Bytes | SHA-256 |
|---|---:|---|
| `SKILL.md` | 11,590 | `7bde48e6e31928f476b45c458696025f2f5b222bb709d8fb2d527e2022e716b5` |
| `reference/ARCHITECTURE.md` | 1,866 | `72c698d84d109dbb074fd33210ece695707e45e313724accfadf679793f82424` |
| `reference/CLASS-ER.md` | 2,049 | `c8a0d2baa3492763b9f916855b21a3be509ff1d6b1b4d2d08d08602cca431651` |
| `reference/FLOWCHART.md` | 1,561 | `f731beefed962d608d5b0d17285e4b22979a25d25ecf29ec3ca9093d5922378f` |
| `reference/OTHER-TYPES.md` | 1,878 | `dbc0e308c0978bbb97db96162d42c602b93593eadac773afc189b13e3f5df637` |
| `reference/SEQUENCE.md` | 1,657 | `48988228c4a927935004222ff8731dfb41b9cc62efe9cf7b4f4536908cd38f1c` |

> The upstream Mermaid instructions mention Kroki/curl, but this project disables that path. A missing local renderer is a gate failure, not permission for network fallback.
