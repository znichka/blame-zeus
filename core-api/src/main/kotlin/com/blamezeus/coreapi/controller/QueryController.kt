package com.blamezeus.coreapi.controller

import com.blamezeus.coreapi.domain.dto.QueryRequest
import com.blamezeus.coreapi.domain.dto.QueryResponse
import com.blamezeus.coreapi.domain.entity.EntityRecord
import com.blamezeus.coreapi.domain.entity.Source
import com.blamezeus.coreapi.repository.EntityRecordRepository
import com.blamezeus.coreapi.repository.SourceRepository
import com.blamezeus.coreapi.service.QueryService
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

// GET /api/v1/conflicts/{entityName} is added in Stage 7 (needs ConflictLookup).
@RestController
@RequestMapping("/api/v1")
class QueryController(
    private val entityRecordRepository: EntityRecordRepository,
    private val sourceRepository: SourceRepository,
    private val queryService: QueryService,
) {

    @GetMapping("/entities")
    fun entities(): List<EntityRecord> = entityRecordRepository.findAll()

    @GetMapping("/sources")
    fun sources(): List<Source> = sourceRepository.findAll()

    @PostMapping("/query")
    fun query(@RequestBody request: QueryRequest): QueryResponse = queryService.handle(request.question)
}
