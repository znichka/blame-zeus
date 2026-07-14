package com.blamezeus.coreapi.repository

import com.blamezeus.coreapi.domain.entity.MythParticipant
import com.blamezeus.coreapi.domain.entity.MythParticipantId
import org.springframework.data.jpa.repository.JpaRepository

interface MythParticipantRepository : JpaRepository<MythParticipant, MythParticipantId>
