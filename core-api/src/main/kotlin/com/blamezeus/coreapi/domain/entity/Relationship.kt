package com.blamezeus.coreapi.domain.entity

import jakarta.persistence.Entity
import jakarta.persistence.GeneratedValue
import jakarta.persistence.GenerationType
import jakarta.persistence.Id
import jakarta.persistence.Table

// Plain FK columns (fromId/toId), not @ManyToOne — avoids N+1 surprises on simple read
// paths (TODO-stage4 D3).
@Entity
@Table(name = "relationships")
class Relationship(
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Int = 0,
    val fromId: Int,
    val relation: String,
    val toId: Int,
    val sourceId: String,
    val passageRef: String? = null,
)
