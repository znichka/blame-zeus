package com.blamezeus.coreapi.repository

import com.blamezeus.coreapi.domain.entity.Myth
import org.springframework.data.jpa.repository.JpaRepository

interface MythRepository : JpaRepository<Myth, Int>
