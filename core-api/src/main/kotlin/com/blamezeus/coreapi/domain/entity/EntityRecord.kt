package com.blamezeus.coreapi.domain.entity

import jakarta.persistence.Entity
import jakarta.persistence.GeneratedValue
import jakarta.persistence.GenerationType
import jakarta.persistence.Id
import jakarta.persistence.Table

// Named EntityRecord, not Entity, to avoid colliding with jakarta.persistence.Entity —
// keep this name through Stage 7 (ConflictLookup, EntityExtractor/ConflictProbe).
@Entity
@Table(name = "entities")
class EntityRecord(
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Int = 0,
    val name: String,
    val type: String,
    val generation: Int? = null,
    val domain: String? = null,
    val subtype: String? = null,
)
