package com.blamezeus.coreapi.repository

import com.blamezeus.coreapi.AbstractContainerTest
import com.blamezeus.coreapi.domain.entity.EntityRecord
import com.blamezeus.coreapi.domain.entity.Myth
import com.blamezeus.coreapi.domain.entity.MythParticipant
import com.blamezeus.coreapi.domain.entity.MythParticipantId
import com.blamezeus.coreapi.domain.entity.Relationship
import com.blamezeus.coreapi.domain.entity.VariantClaim
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate

// Track D verification: no Track C2-C4 seed data exists yet (V10-V12 not built), so
// these exercise each repository against hand-inserted fixture rows rather than the
// real seed. Track G's dedicated per-repository tests (against real seed data) land
// once Track C finishes; this is not a substitute for those.
class RepositoryQueryTest : AbstractContainerTest() {

    @Autowired
    lateinit var entityRecordRepository: EntityRecordRepository

    @Autowired
    lateinit var relationshipRepository: RelationshipRepository

    @Autowired
    lateinit var mythRepository: MythRepository

    @Autowired
    lateinit var mythParticipantRepository: MythParticipantRepository

    @Autowired
    lateinit var variantClaimRepository: VariantClaimRepository

    @Autowired
    lateinit var narrativeChunkRepository: NarrativeChunkRepository

    @Autowired
    lateinit var jdbcTemplate: JdbcTemplate

    @Test
    fun `findByNameIgnoreCase resolves regardless of case`() {
        entityRecordRepository.save(EntityRecord(name = "TestZeusA", type = "olympian"))

        val found = entityRecordRepository.findByNameIgnoreCase("testzeusa")

        assertThat(found).isNotNull
        assertThat(found!!.name).isEqualTo("TestZeusA")
        assertThat(found.type).isEqualTo("olympian")
    }

    @Test
    fun `relationship persists with plain FK columns and real source attribution`() {
        val zeus = entityRecordRepository.save(EntityRecord(name = "TestZeusB", type = "olympian"))
        val hera = entityRecordRepository.save(EntityRecord(name = "TestHeraB", type = "olympian"))

        val saved = relationshipRepository.save(
            Relationship(fromId = zeus.id, relation = "married_to", toId = hera.id, sourceId = "hesiod-theogony")
        )

        val reloaded = relationshipRepository.findById(saved.id).orElseThrow()
        assertThat(reloaded.fromId).isEqualTo(zeus.id)
        assertThat(reloaded.toId).isEqualTo(hera.id)
        assertThat(reloaded.sourceId).isEqualTo("hesiod-theogony")
    }

    @Test
    fun `myth participant round-trips through its composite key`() {
        val myth = mythRepository.save(Myth(title = "Test Myth C"))
        val entity = entityRecordRepository.save(EntityRecord(name = "TestHeroC", type = "hero"))

        val id = MythParticipantId(mythId = myth.id, entityId = entity.id)
        mythParticipantRepository.save(MythParticipant(id = id, role = "protagonist"))

        val reloaded = mythParticipantRepository.findById(id).orElseThrow()
        assertThat(reloaded.role).isEqualTo("protagonist")
    }

    @Test
    fun `findBySubjectEntityIdAndClaimType filters to the matching subject and type`() {
        val subject = entityRecordRepository.save(EntityRecord(name = "TestAphroditeD", type = "olympian"))
        variantClaimRepository.save(
            VariantClaim(
                subjectEntityId = subject.id,
                claimType = "parentage",
                claimValue = "child of Uranus",
                sourceId = "hesiod-theogony",
            )
        )
        variantClaimRepository.save(
            VariantClaim(
                subjectEntityId = subject.id,
                claimType = "marriage",
                claimValue = "married to Hephaestus",
                sourceId = "homer-odyssey",
            )
        )

        val results = variantClaimRepository.findBySubjectEntityIdAndClaimType(subject.id, "parentage")

        assertThat(results).hasSize(1)
        assertThat(results[0].claimValue).isEqualTo("child of Uranus")
    }

    @Test
    fun `findByEntityNameIgnoreCase theta-joins to EntityRecord without a mapped association`() {
        val subject = entityRecordRepository.save(EntityRecord(name = "TestAphroditeE", type = "olympian"))
        variantClaimRepository.save(
            VariantClaim(
                subjectEntityId = subject.id,
                claimType = "parentage",
                claimValue = "child of Uranus",
                sourceId = "hesiod-theogony",
            )
        )
        variantClaimRepository.save(
            VariantClaim(
                subjectEntityId = subject.id,
                claimType = "parentage",
                claimValue = "child of Zeus and Dione",
                sourceId = "homer-iliad",
            )
        )

        val results = variantClaimRepository.findByEntityNameIgnoreCase("testaphroditee")

        assertThat(results).hasSize(2)
        assertThat(results.map { it.sourceId }).containsExactlyInAnyOrder("hesiod-theogony", "homer-iliad")
    }

    @Test
    fun `narrative chunk read-only columns come through after a pipeline-style insert`() {
        // embedding/content_hash are intentionally unmapped/read-only (D6) — the Python
        // pipeline is the real writer, so insert via raw SQL rather than the repository.
        val vectorLiteral = (1..3072).joinToString(",", prefix = "[", postfix = "]") { "0" }
        jdbcTemplate.update(
            "INSERT INTO narrative_chunks (content, embedding, source_id, passage_ref, embedding_model) " +
                "VALUES (?, ?::vector, ?, ?, ?)",
            "Test chunk content for Track D verification.",
            vectorLiteral,
            "apollodorus-bibliotheca",
            "1.1.1",
            "text-embedding-3-large",
        )

        val chunk = narrativeChunkRepository.findAll().first { it.content.startsWith("Test chunk content") }

        assertThat(chunk.sourceId).isEqualTo("apollodorus-bibliotheca")
        assertThat(chunk.passageRef).isEqualTo("1.1.1")
        assertThat(chunk.embeddingModel).isEqualTo("text-embedding-3-large")
        assertThat(chunk.contentHash).isNotNull() // Postgres GENERATED ALWAYS column
    }
}
