package com.blamezeus.coreapi.domain.dto

// `debug` (Stage P2 Track A2) is trailing + defaulted so every existing construction/JSON body
// (no "debug" key) still deserializes to `false` (DEV-064).
data class QueryRequest(val question: String, val debug: Boolean = false)
