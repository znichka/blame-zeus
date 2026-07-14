package com.blamezeus.coreapi.domain.entity

import jakarta.persistence.Entity
import jakarta.persistence.Id
import jakarta.persistence.Table

@Entity
@Table(name = "sources")
class Source(
    @Id
    val id: String,
    val author: String,
    val work: String,
    val passageRef: String? = null,
    val translation: String? = null,
    val stance: String,
    val yearPublished: Int,
    val role: String,
)
