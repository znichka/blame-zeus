package com.blamezeus.coreapi.repository

import com.blamezeus.coreapi.domain.entity.EntityRecord
import org.springframework.data.jpa.repository.JpaRepository

interface EntityRecordRepository : JpaRepository<EntityRecord, Int> {
    fun findByNameIgnoreCase(name: String): EntityRecord?
}
