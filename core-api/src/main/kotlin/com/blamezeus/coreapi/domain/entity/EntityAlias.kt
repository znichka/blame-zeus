package com.blamezeus.coreapi.domain.entity

import jakarta.persistence.Column
import jakarta.persistence.Entity
import jakarta.persistence.GeneratedValue
import jakarta.persistence.GenerationType
import jakarta.persistence.Id
import jakarta.persistence.Table

// Track D7: maps V14__create_entity_aliases.sql. Plain FK column (entityId) rather than a
// @ManyToOne to EntityRecord, matching D3's "prefer plain FK columns over @ManyToOne" rule —
// resolution callers (ConflictLookup) look the aliased entity up by id explicitly.
// Only safe to map now that V14 exists: ddl-auto:validate fails the whole context if an
// @Entity points at a missing table (DEV-037).
@Entity
@Table(name = "entity_aliases")
class EntityAlias(
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Int = 0,
    @Column(name = "entity_id")
    val entityId: Int,
    val alias: String,
)
