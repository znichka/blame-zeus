package com.blamezeus.coreapi.domain.entity

import jakarta.persistence.Column
import jakarta.persistence.Embeddable
import jakarta.persistence.EmbeddedId
import jakarta.persistence.Entity
import jakarta.persistence.Table
import java.io.Serializable

@Embeddable
data class MythParticipantId(
    @Column(name = "myth_id")
    val mythId: Int,
    @Column(name = "entity_id")
    val entityId: Int,
) : Serializable

@Entity
@Table(name = "myth_participants")
class MythParticipant(
    @EmbeddedId
    val id: MythParticipantId,
    val role: String? = null,
)
