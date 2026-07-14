package com.blamezeus.coreapi.repository

import com.blamezeus.coreapi.domain.entity.Relationship
import org.springframework.data.jpa.repository.JpaRepository

interface RelationshipRepository : JpaRepository<Relationship, Int>
