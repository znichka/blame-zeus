package com.blamezeus.coreapi.repository

import com.blamezeus.coreapi.domain.entity.NarrativeChunk
import org.springframework.data.jpa.repository.JpaRepository

interface NarrativeChunkRepository : JpaRepository<NarrativeChunk, Int>
