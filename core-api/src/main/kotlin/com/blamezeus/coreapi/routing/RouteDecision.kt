package com.blamezeus.coreapi.routing

// SQL | RAG | MIXED only — no CONFLICT (ADR-007: conflict surfacing is a router-
// independent enrichment step in QueryService, not a fourth route). Stubbed here in
// Track E (Stage 4) so QueryResponse can be fully typed now instead of a String?
// placeholder; QueryRouter (Stage 5) is the eventual @AiService producer of this enum.
enum class RouteDecision {
    SQL,
    RAG,
    MIXED,
}
