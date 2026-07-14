package com.blamezeus.coreapi.domain.entity

import jakarta.persistence.Entity
import jakarta.persistence.GeneratedValue
import jakarta.persistence.GenerationType
import jakarta.persistence.Id
import jakarta.persistence.Table

@Entity
@Table(name = "variant_claims")
class VariantClaim(
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Int = 0,
    val subjectEntityId: Int,
    val claimType: String,
    val claimValue: String,
    val sourceId: String,
    val trustTier: Short = 2,
    val passageRef: String? = null,
)
