package com.blamezeus.coreapi.repository

import com.blamezeus.coreapi.domain.entity.EntityAlias
import org.springframework.data.jpa.repository.JpaRepository

interface EntityAliasRepository : JpaRepository<EntityAlias, Int> {
    fun findByAliasIgnoreCase(alias: String): EntityAlias?
}
