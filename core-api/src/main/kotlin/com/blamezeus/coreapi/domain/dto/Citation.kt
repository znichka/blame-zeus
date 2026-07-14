package com.blamezeus.coreapi.domain.dto

data class Citation(
    val author: String,
    val work: String,
    val passageRef: String,
    val stance: String? = null,
)
