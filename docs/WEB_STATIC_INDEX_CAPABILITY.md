# Web Static Index Capability

`capability://web.static-index.render` is the shared AgentOS capability for producing a crawler- and AI-readable static representation of a public web route.

## Why this is a capability

Web products should not each embed their own SEO/crawler HTML generator. Product code owns the interactive experience and the public data that may be exposed. This capability owns the reusable static representation contract, escaping, baseline metadata and render receipt.

The consumer flow is:

```text
web/page generation
  -> classify route
  -> resolve capability://web.static-index.render
  -> create agentos.web-static-index/v1 spec
  -> invoke renderer
  -> serve generated HTML as initial representation or deterministic public summary route
  -> verify with no-JavaScript fetch
```

## Input contract

Example:

```json
{
  "schema": "agentos.web-static-index/v1",
  "title": "宅向分析結果",
  "heading": "坐北朝南",
  "summary": "文昌位在東南方。",
  "canonical_url": "https://studio.milkcat.org/fengshui/result/example",
  "lang": "zh-Hant",
  "robots": "index,follow",
  "facts": [
    {"label": "文昌位", "value": "東南方"}
  ],
  "sections": [
    {"heading": "摘要", "text": "這是可公開分享的分析摘要。"}
  ],
  "links": [
    {"label": "開啟互動工具", "url": "https://studio.milkcat.org/fengshui/"}
  ]
}
```

Only data already authorized for public exposure belongs in the spec. Arbitrary raw HTML is intentionally not part of the contract.

## Invocation

The canonical entrypoint is declared in the capability manifest:

```bash
python3 scripts/web_static_index.py \
  --spec page-index.json \
  --output dist/index.html
```

The command emits an `agentos.web-static-index-receipt/v1` receipt containing the capability ID, output path, SHA-256 digest, canonical URL and robots intent.

## Consumer rule

For a `public-discoverable` page, a web-producing AgentOS workflow must resolve and reuse this capability rather than create a product-local crawler renderer. Product-specific code should only map its public result/data model into the capability input.

A `public-noindex` route may use the same renderer with an explicit `noindex` policy. A `private/authenticated` route must not generate a public index artifact from private data.

Machine readability and crawler permission remain separate. Search/archival/AI-training crawler policy is controlled independently; this capability does not grant training permission.

## Acceptance

A public-discoverable route is not accepted merely because the dynamic application works or returns HTTP 200. Acceptance requires:

1. the static-index render receipt;
2. a no-JavaScript HTTP fetch that exposes title, H1, summary, canonical URL and robots intent;
3. no leakage of private/user/account/internal state;
4. crawler/sitemap/canonical behavior consistent with the declared route class.
