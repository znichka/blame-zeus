package com.blamezeus.coreapi.controller

import com.blamezeus.coreapi.ai.ConflictSynthesizer
import com.blamezeus.coreapi.conflict.ConflictLookup
import com.blamezeus.coreapi.domain.dto.ConflictEntry
import com.blamezeus.coreapi.domain.dto.QueryRequest
import com.blamezeus.coreapi.domain.dto.QueryResponse
import com.blamezeus.coreapi.domain.entity.EntityRecord
import com.blamezeus.coreapi.domain.entity.Source
import com.blamezeus.coreapi.repository.EntityRecordRepository
import com.blamezeus.coreapi.repository.SourceRepository
import com.blamezeus.coreapi.service.QueryService
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/api/v1")
class QueryController(
    private val entityRecordRepository: EntityRecordRepository,
    private val sourceRepository: SourceRepository,
    private val queryService: QueryService,
    private val conflictLookup: ConflictLookup,
    private val conflictSynthesizer: ConflictSynthesizer,
) {

    @GetMapping("/entities")
    fun entities(): List<EntityRecord> = entityRecordRepository.findAll()

    @GetMapping("/sources")
    fun sources(): List<Source> = sourceRepository.findAll()

    @PostMapping("/query")
    fun query(@RequestBody request: QueryRequest): QueryResponse = queryService.handle(request.question, request.debug)

    // Stage 7 Track F: the one caller of ConflictLookup's subject-only fetch (ADR-007 §5) — an
    // explicit by-entity dev/demo lookup across every claim_type, never wired into the per-query
    // enrichment step, so it can never pollute a grounded refusal. Deliberately 200 + empty list
    // for an unresolvable name rather than 404: ConflictLookup can't distinguish "no such entity"
    // from "a real entity with zero recorded conflicts" (both resolve to an empty list), and a 404
    // would misreport the latter case as nonexistent — an empty array is honest for both.
    @GetMapping("/conflicts/{entityName}")
    fun conflicts(@PathVariable entityName: String): List<ConflictEntry> =
        conflictSynthesizer.synthesize(conflictLookup.findAllForEntity(entityName))
}
