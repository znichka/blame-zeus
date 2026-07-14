package com.blamezeus.coreapi.controller

import com.blamezeus.coreapi.domain.entity.EntityRecord
import com.blamezeus.coreapi.domain.entity.Source
import com.blamezeus.coreapi.repository.EntityRecordRepository
import com.blamezeus.coreapi.repository.SourceRepository
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

// POST /api/v1/query and GET /api/v1/conflicts/{entityName} are added in later stages
// (Stage 5 needs QueryService; Stage 7 needs ConflictLookup) — this is a skeleton plus
// the two read endpoints Track F actually calls for now.
@RestController
@RequestMapping("/api/v1")
class QueryController(
    private val entityRecordRepository: EntityRecordRepository,
    private val sourceRepository: SourceRepository,
) {

    @GetMapping("/entities")
    fun entities(): List<EntityRecord> = entityRecordRepository.findAll()

    @GetMapping("/sources")
    fun sources(): List<Source> = sourceRepository.findAll()
}
