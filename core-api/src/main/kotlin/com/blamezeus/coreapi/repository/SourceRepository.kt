package com.blamezeus.coreapi.repository

import com.blamezeus.coreapi.domain.entity.Source
import org.springframework.data.jpa.repository.JpaRepository

interface SourceRepository : JpaRepository<Source, String>
