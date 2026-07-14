package com.blamezeus.coreapi.domain.dto

data class RagResponse(
    val answer: String,
    val citations: List<Citation>,
)
