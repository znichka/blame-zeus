package com.blamezeus.coreapi.domain.dto

// ADR-015 Track A1/B2: AnswerComposer's output shape. Reuses the existing Citation type (author,
// work, passageRef, stance?) so the composer's unified references match what the template already
// renders — no separate citation type for the composition stage.
data class ComposedAnswer(
    val answer: String,
    val citations: List<Citation>,
)
