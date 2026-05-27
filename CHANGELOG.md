# Changelog

Tutte le release di `DocMolder` sono tracciate qui.

Il changelog segue un flusso orientato a GitHub:

- le versioni sono gestite con Semantic Versioning
- le release sono preparate da `release-please`
- il contenuto deriva dai merge su `main` con titolo/commit in formato Conventional Commits

## [2.0.3](https://github.com/max23468/DocMolder/compare/docmolder-v2.0.2...docmolder-v2.0.3) (2026-05-27)


### Documentazione

* align Atlas semantic governance [skip ci] ([ff26f1f](https://github.com/max23468/DocMolder/commit/ff26f1f458bd75165401aadf2842f1cc245b6bdc))

## [2.0.2](https://github.com/max23468/DocMolder/compare/docmolder-v2.0.1...docmolder-v2.0.2) (2026-05-23)


### Correzioni

* **ops:** restore Python 3.11 installer fallback ([#164](https://github.com/max23468/DocMolder/issues/164)) ([c951f68](https://github.com/max23468/DocMolder/commit/c951f687727820eaa890de2f238d0bab863dc25a))

## [2.0.1](https://github.com/max23468/DocMolder/compare/docmolder-v2.0.0...docmolder-v2.0.1) (2026-05-23)


### Correzioni

* **ops:** migrate runtime to Python 3.13 ([#162](https://github.com/max23468/DocMolder/issues/162)) ([bc9058f](https://github.com/max23468/DocMolder/commit/bc9058f39b175934363743f57f9db02dfa6f5d0d))

## [2.0.0](https://github.com/max23468/DocMolder/compare/docmolder-v1.7.3...docmolder-v2.0.0) (2026-05-23)


### ⚠ BREAKING CHANGES

* **excel:** DocMolder no longer supports Excel .xlsb files. Users must export binary workbooks to .xlsx, .xlsm, or .xls before using the Excel unlock action.

### Funzionalità

* **excel:** remove xlsb and Aspose support ([#160](https://github.com/max23468/DocMolder/issues/160)) ([f3898f8](https://github.com/max23468/DocMolder/commit/f3898f80d0e66ab6dffc264c02f1db2ea0cc3ba6))

## [1.7.3](https://github.com/max23468/DocMolder/compare/docmolder-v1.7.2...docmolder-v1.7.3) (2026-05-08)


### Correzioni

* **excel:** report password-protected XLSB sheets ([#154](https://github.com/max23468/DocMolder/issues/154)) ([305a06f](https://github.com/max23468/DocMolder/commit/305a06f840881e75e1a14187edd526b2d467d7d6))

## [1.7.2](https://github.com/max23468/DocMolder/compare/docmolder-v1.7.1...docmolder-v1.7.2) (2026-05-08)


### Correzioni

* **excel:** gate XLSB unlock behind licensed engine ([#152](https://github.com/max23468/DocMolder/issues/152)) ([1fd1d68](https://github.com/max23468/DocMolder/commit/1fd1d686ddbbacf27b3cc67b0d91ed67030eec26))

## [1.7.1](https://github.com/max23468/DocMolder/compare/docmolder-v1.7.0...docmolder-v1.7.1) (2026-05-08)


### Correzioni

* **bot:** preserve Excel suffix inferred from MIME ([#150](https://github.com/max23468/DocMolder/issues/150)) ([4921e2a](https://github.com/max23468/DocMolder/commit/4921e2ab4a51a4907d376a808e6ccf40b80cd887))

## [1.7.0](https://github.com/max23468/DocMolder/compare/docmolder-v1.6.5...docmolder-v1.7.0) (2026-05-08)


### Funzionalità

* support Excel editing unlock ([#146](https://github.com/max23468/DocMolder/issues/146)) ([40fe53b](https://github.com/max23468/DocMolder/commit/40fe53b20e24e60923bf44f09f3011347e8edfe8))

## [1.6.5](https://github.com/max23468/DocMolder/compare/docmolder-v1.6.4...docmolder-v1.6.5) (2026-05-02)


### Correzioni

* preserve venv dir on empty env override ([#134](https://github.com/max23468/DocMolder/issues/134)) ([d187caa](https://github.com/max23468/DocMolder/commit/d187caaa39e8b7fc1ef1e484bf24c5aa1620e491))

## [1.6.4](https://github.com/max23468/DocMolder/compare/docmolder-v1.6.3...docmolder-v1.6.4) (2026-05-02)


### Correzioni

* resolve historical Codex bot review findings ([#132](https://github.com/max23468/DocMolder/issues/132)) ([322b36d](https://github.com/max23468/DocMolder/commit/322b36d6b268351e30b44d4189fea25ba9aabd94))

## [1.6.3](https://github.com/max23468/DocMolder/compare/docmolder-v1.6.2...docmolder-v1.6.3) (2026-05-01)


### Correzioni

* **processing:** keep PDF crop content-safe ([#125](https://github.com/max23468/DocMolder/issues/125)) ([a1faa4e](https://github.com/max23468/DocMolder/commit/a1faa4e0a84595cdb7af8a34e178b04bec583db0))

## [1.6.2](https://github.com/max23468/DocMolder/compare/docmolder-v1.6.1...docmolder-v1.6.2) (2026-05-01)


### Correzioni

* **processing:** improve PDF crop for photo borders ([#123](https://github.com/max23468/DocMolder/issues/123)) ([d7384bb](https://github.com/max23468/DocMolder/commit/d7384bb4c61047bec3bfdd437bb1ab602bdd021c))

## [1.6.1](https://github.com/max23468/DocMolder/compare/docmolder-v1.6.0...docmolder-v1.6.1) (2026-05-01)


### Correzioni

* **bot:** clarify image crop reruns ([#121](https://github.com/max23468/DocMolder/issues/121)) ([25748ef](https://github.com/max23468/DocMolder/commit/25748ef9f74773dbd4b340ff22fc36ab1243e01e))

## [1.6.0](https://github.com/max23468/DocMolder/compare/docmolder-v1.5.2...docmolder-v1.6.0) (2026-05-01)


### Funzionalità

* supporta il taglio bordi dei PDF ([#119](https://github.com/max23468/DocMolder/issues/119)) ([93b488c](https://github.com/max23468/DocMolder/commit/93b488c776b3befff8d0ddd7714c4b38bbb5a5c5))

## [1.5.2](https://github.com/max23468/DocMolder/compare/docmolder-v1.5.1...docmolder-v1.5.2) (2026-05-01)


### Correzioni

* **reliability:** harden release sanity and file errors ([#117](https://github.com/max23468/DocMolder/issues/117)) ([1d63ce0](https://github.com/max23468/DocMolder/commit/1d63ce0f3ae294d6bf0c8bc8a47d61d6fe4e6d03))

## [1.5.1](https://github.com/max23468/DocMolder/compare/docmolder-v1.5.0...docmolder-v1.5.1) (2026-04-28)


### Correzioni

* **copy:** correct Italian accents and grammar ([#112](https://github.com/max23468/DocMolder/issues/112)) ([778da68](https://github.com/max23468/DocMolder/commit/778da68d9d8888ca78e4f316ac4f2dd2dc87c9e4))

## [1.5.0](https://github.com/max23468/DocMolder/compare/docmolder-v1.4.0...docmolder-v1.5.0) (2026-04-28)


### Funzionalità

* **ops:** add public scale guardrails ([#111](https://github.com/max23468/DocMolder/issues/111)) ([8d1a5ac](https://github.com/max23468/DocMolder/commit/8d1a5acd142d6d28d083ac203999d171224bfec6))

## [1.4.0](https://github.com/max23468/DocMolder/compare/docmolder-v1.3.0...docmolder-v1.4.0) (2026-04-28)


### Funzionalità

* **scans:** improve document photo quality feedback ([#110](https://github.com/max23468/DocMolder/issues/110)) ([5405513](https://github.com/max23468/DocMolder/commit/5405513eec61650d20811b23b90dee23838b6b51))

## [1.3.0](https://github.com/max23468/DocMolder/compare/docmolder-v1.2.0...docmolder-v1.3.0) (2026-04-28)


### Funzionalità

* **presets:** add lightweight user presets ([#109](https://github.com/max23468/DocMolder/issues/109)) ([151946e](https://github.com/max23468/DocMolder/commit/151946e554785cf031a502ad511b8fcd13192aae))

## [1.2.0](https://github.com/max23468/DocMolder/compare/docmolder-v1.1.0...docmolder-v1.2.0) (2026-04-28)


### Funzionalità

* **ux:** clarify public onboarding and trust signals ([#108](https://github.com/max23468/DocMolder/issues/108)) ([8077dad](https://github.com/max23468/DocMolder/commit/8077dad8504494ab64d53e00a0a1e3186136a7dd))

## [1.1.0](https://github.com/max23468/DocMolder/compare/docmolder-v1.0.1...docmolder-v1.1.0) (2026-04-28)


### Funzionalità

* **data:** add self-service data deletion and job retention ([#107](https://github.com/max23468/DocMolder/issues/107)) ([045565d](https://github.com/max23468/DocMolder/commit/045565d9fee985b9494c85f65ca3c9763d08cfc7))

## [1.0.1](https://github.com/max23468/DocMolder/compare/docmolder-v1.0.0...docmolder-v1.0.1) (2026-04-28)


### Documentazione

* **release:** delay target cleanup until release completes ([#106](https://github.com/max23468/DocMolder/issues/106)) ([4972bbe](https://github.com/max23468/DocMolder/commit/4972bbe92583be9ecb95d0b37e2500beddae52f8))

## [1.0.0](https://github.com/max23468/DocMolder/compare/docmolder-v0.12.2...docmolder-v1.0.0) (2026-04-28)


### Documentazione

* **release:** prepare DocMolder 1.0 ([#105](https://github.com/max23468/DocMolder/issues/105)) ([207344b](https://github.com/max23468/DocMolder/commit/207344b219c0050532373a2659c09b8d101ad16e))

## [0.12.2](https://github.com/max23468/DocMolder/compare/docmolder-v0.12.1...docmolder-v0.12.2) (2026-04-28)


### Documentazione

* **release:** define major release criteria ([#104](https://github.com/max23468/DocMolder/issues/104)) ([b7fd8d3](https://github.com/max23468/DocMolder/commit/b7fd8d351df45875e1745ae32cdcff8a5be19681))

## [0.12.1](https://github.com/max23468/DocMolder/compare/docmolder-v0.12.0...docmolder-v0.12.1) (2026-04-28)


### Correzioni

* **release:** support explicit 1.0 graduation target ([#103](https://github.com/max23468/DocMolder/issues/103)) ([da4f448](https://github.com/max23468/DocMolder/commit/da4f448bdd6fc85dde864ffb614ac53992b8cb89))

## [0.12.0](https://github.com/max23468/DocMolder/compare/docmolder-v0.11.9...docmolder-v0.12.0) (2026-04-28)


### Funzionalità

* complete phase 8 runtime optimization ([#102](https://github.com/max23468/DocMolder/issues/102)) ([c1470cb](https://github.com/max23468/DocMolder/commit/c1470cb92fd5875714a287f4e04dc54a446b63a7))

## [0.11.9](https://github.com/max23468/DocMolder/compare/docmolder-v0.11.8...docmolder-v0.11.9) (2026-04-28)


### Correzioni

* **deploy:** preserve webhook worker restart flag ([#101](https://github.com/max23468/DocMolder/issues/101)) ([b6e36f3](https://github.com/max23468/DocMolder/commit/b6e36f3781811a7c3b264d449ce6795ec0b436a5))

## [0.11.8](https://github.com/max23468/DocMolder/compare/docmolder-v0.11.7...docmolder-v0.11.8) (2026-04-28)


### Correzioni

* **ops:** realign release and webhook flows ([#100](https://github.com/max23468/DocMolder/issues/100)) ([008d25a](https://github.com/max23468/DocMolder/commit/008d25a1915b37b2404e87e96da7da38f298af6b))

## [0.11.7](https://github.com/max23468/DocMolder/compare/docmolder-v0.11.6...docmolder-v0.11.7) (2026-04-28)


### Correzioni

* **security:** avoid logging release tokens ([#99](https://github.com/max23468/DocMolder/issues/99)) ([5179f9c](https://github.com/max23468/DocMolder/commit/5179f9c8dfa6045c0079167505e3bb335b34905c))

## [0.11.6](https://github.com/max23468/DocMolder/compare/docmolder-v0.11.5...docmolder-v0.11.6) (2026-04-28)


### Correzioni

* **release:** simplify local-first publish flow ([#98](https://github.com/max23468/DocMolder/issues/98)) ([b303121](https://github.com/max23468/DocMolder/commit/b303121b9bbf15f8bc695dfbfbb358933945e88d))

## [0.11.5](https://github.com/max23468/DocMolder/compare/docmolder-v0.11.4...docmolder-v0.11.5) (2026-04-28)


### Correzioni

* **bot:** simplify Telegram command surfaces ([#97](https://github.com/max23468/DocMolder/issues/97)) ([3bbed81](https://github.com/max23468/DocMolder/commit/3bbed817d41025071828f3c5529290e047986131))

## [0.11.4](https://github.com/max23468/DocMolder/compare/docmolder-v0.11.3...docmolder-v0.11.4) (2026-04-27)


### Correzioni

* **release:** preserve custom git token env ([#96](https://github.com/max23468/DocMolder/issues/96)) ([0cee5d5](https://github.com/max23468/DocMolder/commit/0cee5d55d079c318e77b4c30a81ba64ef79fabcf))

## [0.11.3](https://github.com/max23468/DocMolder/compare/docmolder-v0.11.2...docmolder-v0.11.3) (2026-04-27)


### Correzioni

* **release:** defer webhook restart after deploy ([#95](https://github.com/max23468/DocMolder/issues/95)) ([e14279d](https://github.com/max23468/DocMolder/commit/e14279de6d3ed3ad242fe8b58861c04cc2cb20d3))

## [0.11.2](https://github.com/max23468/DocMolder/compare/docmolder-v0.11.1...docmolder-v0.11.2) (2026-04-27)


### Correzioni

* **release:** preserve release env through sudo ([#94](https://github.com/max23468/DocMolder/issues/94)) ([b4c29c7](https://github.com/max23468/DocMolder/commit/b4c29c7cbad7b32a51e2bad16aac7b45f0830495))

## [0.11.1](https://github.com/max23468/DocMolder/compare/docmolder-v0.11.0...docmolder-v0.11.1) (2026-04-27)


### Correzioni

* **release:** avoid restarting webhook during deploy ([#92](https://github.com/max23468/DocMolder/issues/92)) ([23cd845](https://github.com/max23468/DocMolder/commit/23cd84592a182a371830305867906fcce1c76b0f))
* **release:** separate API and git release tokens ([#93](https://github.com/max23468/DocMolder/issues/93)) ([786377f](https://github.com/max23468/DocMolder/commit/786377f22c1e8d0f5fb70b951c5ee2cbae2213f0))

## [0.11.0](https://github.com/max23468/DocMolder/compare/docmolder-v0.10.1...docmolder-v0.11.0) (2026-04-28)


### Funzionalità

* **site:** publish privacy page and duckdns units (#85) [skip ci] ([a1faa27](https://github.com/max23468/DocMolder/commit/a1faa271fd1c60c1b7723dac2c36f70a17e9865b))

### Correzioni

* **release:** automate VPS releases without Actions ([#88](https://github.com/max23468/DocMolder/issues/88)) ([cc7ba6e](https://github.com/max23468/DocMolder/commit/cc7ba6e41fd497a3e7311c00181f1b344923b408))
* **site:** add favicon.ico fallback for static pages ([#89](https://github.com/max23468/DocMolder/issues/89)) ([f2157ab](https://github.com/max23468/DocMolder/commit/f2157abdcb9334608a539dfcadca37a2611a6c04))
* **release:** run VPS auto-release as app user ([#91](https://github.com/max23468/DocMolder/issues/91)) ([862e0c2](https://github.com/max23468/DocMolder/commit/862e0c23c481ff1800defd805f493d07ce832f2a))

### Documentazione

* close privacy duckdns handoff [skip ci] ([d5c24b3](https://github.com/max23468/DocMolder/commit/d5c24b3ee98b5e7bdc8051f158ba762f014f82a3))

## [0.10.1](https://github.com/max23468/DocMolder/compare/docmolder-v0.10.0...docmolder-v0.10.1) (2026-04-27)


### Correzioni

* **deploy:** guard static site install root ([#82](https://github.com/max23468/DocMolder/issues/82)) ([495ffa3](https://github.com/max23468/DocMolder/commit/495ffa3b48ce295164661b2d9df8fe262391dd05))

## [0.10.0](https://github.com/max23468/DocMolder/compare/docmolder-v0.9.1...docmolder-v0.10.0) (2026-04-27)


### Funzionalità

* **site:** publish static DocMolder landing page ([#80](https://github.com/max23468/DocMolder/issues/80)) ([e4a151d](https://github.com/max23468/DocMolder/commit/e4a151dfd9e9ed87753373f4dcdf5f4852b7a8b1))

## [0.9.1](https://github.com/max23468/DocMolder/compare/docmolder-v0.9.0...docmolder-v0.9.1) (2026-04-25)


### Correzioni

* address late review safeguards ([#74](https://github.com/max23468/DocMolder/issues/74)) ([b430d5b](https://github.com/max23468/DocMolder/commit/b430d5bf0ed6ff189ec8583a49d2ea3e370789ad))

## [0.9.0](https://github.com/max23468/DocMolder/compare/docmolder-v0.8.1...docmolder-v0.9.0) (2026-04-24)


### Funzionalità

* strengthen VPS health and performance safeguards ([#67](https://github.com/max23468/DocMolder/issues/67)) ([4866e62](https://github.com/max23468/DocMolder/commit/4866e628c0664cc4afc05d19b708d50a838ec8b7))


### Documentazione

* document GitHub ready fallback ([#66](https://github.com/max23468/DocMolder/issues/66)) ([828273b](https://github.com/max23468/DocMolder/commit/828273b99c6a837c71e6667b5639f2520648eefa))
* remove deploy consent prompt rules ([#62](https://github.com/max23468/DocMolder/issues/62)) ([add2a0c](https://github.com/max23468/DocMolder/commit/add2a0c83b5c46309c9bc4e2e805e521602b2271))

## [0.8.1](https://github.com/max23468/DocMolder/compare/docmolder-v0.8.0...docmolder-v0.8.1) (2026-04-24)


### Correzioni

* address open Codex bot review findings ([#58](https://github.com/max23468/DocMolder/issues/58)) ([a3441f4](https://github.com/max23468/DocMolder/commit/a3441f4669b1a9876b31bc6d95a700c09b953df6))

## [0.8.0](https://github.com/max23468/DocMolder/compare/docmolder-v0.7.0...docmolder-v0.8.0) (2026-04-24)


### Funzionalità

* **bot:** raddrizza foto documento ([#54](https://github.com/max23468/DocMolder/issues/54)) ([569e86a](https://github.com/max23468/DocMolder/commit/569e86a6c8e022f34744c6e930c77e59cf633877))


### Documentazione

* update publish instructions ([06c76fb](https://github.com/max23468/DocMolder/commit/06c76fb6481100fa62656d25d9c60c9d420b3c6f))

## [0.7.0](https://github.com/max23468/DocMolder/compare/docmolder-v0.6.2...docmolder-v0.7.0) (2026-04-24)


### Funzionalità

* migliora i riferimenti contestuali in chat ([#51](https://github.com/max23468/DocMolder/issues/51)) ([3d8031a](https://github.com/max23468/DocMolder/commit/3d8031a2a449bde1e9f38ded0fc0c6739355bedc))

## [0.6.2](https://github.com/max23468/DocMolder/compare/docmolder-v0.6.1...docmolder-v0.6.2) (2026-04-23)


### Documentazione

* consolidate agent instructions in root ([#44](https://github.com/max23468/DocMolder/issues/44)) ([d36c475](https://github.com/max23468/DocMolder/commit/d36c4754663a54efd2a52ce622a0857dac340694))

## [0.6.1](https://github.com/max23468/DocMolder/compare/docmolder-v0.6.0...docmolder-v0.6.1) (2026-04-23)


### Correzioni

* **deploy:** isolate wrapper command overrides ([#39](https://github.com/max23468/DocMolder/issues/39)) ([3470cf0](https://github.com/max23468/DocMolder/commit/3470cf07f92b7b9f930f0c9937bfbcf67f0c5932))
* **deploy:** load VPS env without sourcing commands ([#43](https://github.com/max23468/DocMolder/issues/43)) ([d105cfc](https://github.com/max23468/DocMolder/commit/d105cfcb315124690af04f4e5349d96dc5d4c7fe))
* **deploy:** run VPS healthcheck directly ([#42](https://github.com/max23468/DocMolder/issues/42)) ([0f00ef2](https://github.com/max23468/DocMolder/commit/0f00ef29f7630bb9dc2e3dc4800b78e46a35b358))
* **deploy:** use fixed wrapper binaries ([#41](https://github.com/max23468/DocMolder/issues/41)) ([36b8d2a](https://github.com/max23468/DocMolder/commit/36b8d2acad568e7c2156d71877a44200747ed2d0))

## [0.6.0](https://github.com/max23468/DocMolder/compare/docmolder-v0.5.4...docmolder-v0.6.0) (2026-04-23)


### Funzionalità

* **ops:** add operational governance and access controls ([#36](https://github.com/max23468/DocMolder/issues/36)) ([2622ccc](https://github.com/max23468/DocMolder/commit/2622ccc108be74b5f6c8ae61351f0bdf78fc1a29))


### Documentazione

* add GitHub failed run guard ([830e20d](https://github.com/max23468/DocMolder/commit/830e20d5a92de77ea5886818003ef0eb92049f74))
* clarify GitHub upload flow ([#38](https://github.com/max23468/DocMolder/issues/38)) ([f9392b0](https://github.com/max23468/DocMolder/commit/f9392b0d91a5990bc596c6d1b6f33d29120930f3))

## [0.5.4](https://github.com/max23468/DocMolder/compare/docmolder-v0.5.3...docmolder-v0.5.4) (2026-04-23)


### Documentazione

* **release:** make release changelogs reader-oriented ([#33](https://github.com/max23468/DocMolder/issues/33)) ([c262ced](https://github.com/max23468/DocMolder/commit/c262cedd70c97926820ca8b7cfcf0bcf1b9f6aa0))

## [0.5.3](https://github.com/max23468/DocMolder/compare/docmolder-v0.5.2...docmolder-v0.5.3) (2026-04-23)


### Fixes

* address pending bot review comments ([#31](https://github.com/max23468/DocMolder/issues/31)) ([761f683](https://github.com/max23468/DocMolder/commit/761f683f2bf8a0758d09a195ed96aff8a7d6d6ac))

## [0.5.2](https://github.com/max23468/DocMolder/compare/docmolder-v0.5.1...docmolder-v0.5.2) (2026-04-23)


### Docs

* handle pending bot review comments ([#29](https://github.com/max23468/DocMolder/issues/29)) ([e6aae40](https://github.com/max23468/DocMolder/commit/e6aae402363451d53d7a738d2b304a9e1508872a))

## [0.5.1](https://github.com/max23468/DocMolder/compare/docmolder-v0.5.0...docmolder-v0.5.1) (2026-04-23)


### Fixes

* handle split output edge cases ([#27](https://github.com/max23468/DocMolder/issues/27)) ([b9a66e0](https://github.com/max23468/DocMolder/commit/b9a66e0e5428a15bc2c3a25ff11b4f862dfbea02))

## [0.5.0](https://github.com/max23468/DocMolder/compare/docmolder-v0.4.1...docmolder-v0.5.0) (2026-04-23)


### Features

* add optional zip output for PDF split ([#24](https://github.com/max23468/DocMolder/issues/24)) ([c5ee9a3](https://github.com/max23468/DocMolder/commit/c5ee9a3a5990290f9eab94dfc31f4243157d11fc))


### Docs

* add internal review rule ([#23](https://github.com/max23468/DocMolder/issues/23)) ([2b6aa35](https://github.com/max23468/DocMolder/commit/2b6aa351def281b65a2e432dc31344e4c376b1be))
* automate release PR follow-through ([#26](https://github.com/max23468/DocMolder/issues/26)) ([e9cac6f](https://github.com/max23468/DocMolder/commit/e9cac6f7a77a865b358b103eedfc9cb2e6a7549a))
* clarify squash merge subject requirements ([#22](https://github.com/max23468/DocMolder/issues/22)) ([689bdcb](https://github.com/max23468/DocMolder/commit/689bdcbd788455208fd63a202fb09c108c2bf62c))
* update agent operating guidelines ([a913ff3](https://github.com/max23468/DocMolder/commit/a913ff3bbf4cf849856acf59e4e2679c446db211))

## [0.4.1](https://github.com/max23468/DocMolder/compare/docmolder-v0.4.0...docmolder-v0.4.1) (2026-04-20)


### Fixes

* **release:** harden release-please guardrails ([#18](https://github.com/max23468/DocMolder/issues/18)) ([398acf9](https://github.com/max23468/DocMolder/commit/398acf92db6372bb360a5f37a64f2c2d6c484ff5))

## [0.4.0](https://github.com/max23468/DocMolder/compare/docmolder-v0.3.0...docmolder-v0.4.0) (2026-04-20)


### Features

* **telegram:** improve bot operations and bump version to 0.4.0 ([#16](https://github.com/max23468/DocMolder/issues/16)) ([e98b068](https://github.com/max23468/DocMolder/commit/e98b06875d58dfdb93d237b74716f3b0250ba866))


### Fixes

* **release:** realign release-please to tagged version ([#17](https://github.com/max23468/DocMolder/issues/17)) ([78a9491](https://github.com/max23468/DocMolder/commit/78a9491dd54a01cfb4078754a1ba61254c37bc04))


### Docs

* **release:** require squash PRs for main ([1428e4f](https://github.com/max23468/DocMolder/commit/1428e4f8cfca204abe7e20ebd7bc1bc03566302a))

## [Unreleased]

## [0.3.0](https://github.com/max23468/DocMolder/compare/docmolder-v0.2.0...docmolder-v0.3.0) (2026-04-20)

### Features

- parser testuale piu robusto per richieste naturali su PDF e immagini, con sinonimi aggiuntivi e tolleranza leggera ai refusi comuni
- estrazione diretta da testo di selezione pagine, gradi di rotazione, watermark e livello di compressione
- chiarimenti guidati e passaggi a input pending quando la richiesta e ambigua o incompleta
- brand system DocMolder con asset dedicati e sincronizzazione di nome, descrizione, comandi e menu del profilo Telegram

### Fixes

- affinata la chiarezza del logo e la qualita di export degli asset brand
- corretto l'avatar Telegram con varianti a fondo pieno per evitare aloni chiari dovuti alla trasparenza
- riallineata l'operativita VPS per deploy e gestione delle variabili ambiente del bot

### Docs

- roadmap, contesto, README e linee guida brand riallineati al completamento della Fase 3

## [0.2.0](https://github.com/max23468/DocMolder/compare/docmolder-v0.1.0...docmolder-v0.2.0) (2026-04-18)


### Features

* aggiunge layout guidato e auto-orientamento PDF ([25c3eb2](https://github.com/max23468/DocMolder/commit/25c3eb29d9508b3a628d2e74a2bee302ba1e1b07))
* completa la fase 1 su affidabilità e fallback PDF ([c98bd82](https://github.com/max23468/DocMolder/commit/c98bd82ba7f81ca49196c57c11b91c2600be2fcf))
* completa la fase 2 su osservabilita e operativita admin ([1913ce1](https://github.com/max23468/DocMolder/commit/1913ce135bdb077ad8c598db8a29b3891aee8b5f))
* completa la fase 3 con funzioni pdf avanzate ([b0f6c9c](https://github.com/max23468/DocMolder/commit/b0f6c9c15feb622190953288d9881826a0a618b6))
* **release:** automate versioning and changelog ([#12](https://github.com/max23468/DocMolder/issues/12)) ([0208942](https://github.com/max23468/DocMolder/commit/020894204d629d63d06bdc52250c937fe04d00f0))


### Fixes

* evita riepiloghi admin periodici vuoti ([b9777fa](https://github.com/max23468/DocMolder/commit/b9777fa237a359fc6dbe8b6a25577b0963a0b6d8))
* redact telegram token from logs ([01b6880](https://github.com/max23468/DocMolder/commit/01b6880a42a0f25743a991d6081347a92653513d))


### Docs

* add minimal root AGENTS pointer to docs ([4a3adaa](https://github.com/max23468/DocMolder/commit/4a3adaa79d18d7a231a97a6e7ecfadf5f54e1c56))
* add root AGENTS guidelines for Codex workflow ([a5494c9](https://github.com/max23468/DocMolder/commit/a5494c917524604b026a8af1adbaa597d4f06faa))
* AGENTS.md root minimal pointer to docs/AGENTS.md ([663a34b](https://github.com/max23468/DocMolder/commit/663a34bc1a331f23268ed1a538a96c16de4256b2))
* aggiorna context del flusso PDF ([a69e750](https://github.com/max23468/DocMolder/commit/a69e7505bf864765055a590401a00087794e8609))
* aggiorna la roadmap dopo i test manuali ([0ddfde3](https://github.com/max23468/DocMolder/commit/0ddfde34ce702c1311c578e9569877589e00db06))
* aggiorna roadmap e README ([72ec030](https://github.com/max23468/DocMolder/commit/72ec030712fb2656359420c9153d602025ddb838))
* amplia e uniforma la documentazione ([53db63b](https://github.com/max23468/DocMolder/commit/53db63be49feeef7c2a9b757b86aeca2a5509809))
* amplia la roadmap con ottimizzazioni operative ([147d1fd](https://github.com/max23468/DocMolder/commit/147d1fd0c1d0cd5e2e5e9e91749dfc1d184a3f52))
* chiarisce il flusso corretto di release ([8fff46e](https://github.com/max23468/DocMolder/commit/8fff46eae23f71b95cb868fb658dc29af1431a0e))
* consolidate runbooks and remove unused tmp assets ([5ca2dca](https://github.com/max23468/DocMolder/commit/5ca2dca942dfd9b14dd067e390b98beaa992e069))
* definisce perimetro prodotto e nuova roadmap ([2409de1](https://github.com/max23468/DocMolder/commit/2409de11c4f9169f6c820e0644e390d066b4c1d6))
* rifinisce la roadmap finale ([846f870](https://github.com/max23468/DocMolder/commit/846f870305a020351334eb4cf19ac72e5712868d))

## [0.1.0] - 2026-04-18

Release baseline che consolida lo stato attuale del progetto prima dell'automazione delle release.

### Added

- bot Telegram funzionante per trasformazioni documentali guidate su PDF e immagini
- creazione PDF da immagini con scelta tra formato originale e impaginazione A4
- unione PDF, estrazione pagine, riordino pagine, eliminazione pagine, rotazione manuale e watermark testuale
- conversione PDF in scala di grigi, compressione su richiesta e correzione automatica dell'orientamento nei flussi compatibili
- storico degli ultimi job con dettaglio essenziale e possibilita di rilancio
- report admin e storage meta persistente per stato operativo e riepiloghi periodici
- workflow GitHub di CI, template issue/PR e documentazione operativa per il mantenimento del repository
- strategia di smoke test post-deploy e script `scripts/smoke_telegram_desktop.py` per automatizzare i controlli principali via Telegram Desktop

### Changed

- flussi utente, recap sessione, prompt guidati e messaggi di stato resi piu espliciti e coerenti
- pipeline PDF resa piu conservativa con fallback piu robusti e gestione errori/cleanup piu solida
- naming degli output, catalogo azioni e storico lavori resi piu leggibili e consistenti
- README e documentazione interna riallineati alle funzionalita realmente disponibili

### Technical

- ampliata la copertura test su pipeline PDF, job flow, storico, timeout, cleanup e smoke test automatizzati
- formalizzata la base per processi GitHub piu strutturati in vista di release versionate
