package com.blamezeus.coreapi.conflict

import com.blamezeus.coreapi.AbstractContainerTest
import com.blamezeus.coreapi.domain.entity.EntityAlias
import com.blamezeus.coreapi.domain.entity.EntityRecord
import com.blamezeus.coreapi.domain.entity.VariantClaim
import com.blamezeus.coreapi.repository.EntityAliasRepository
import com.blamezeus.coreapi.repository.EntityRecordRepository
import com.blamezeus.coreapi.repository.VariantClaimRepository
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired

// Stage 7 Track D1. Real seeded corpus (V10-V14) already carries the Aphrodite/Achilles/Io
// conflicts (VariantClaimRepositoryTest/EntityAliasRepositoryTest reuse it with no fixture
// seeding), so cases (a)/(b)/(c)/(e)/(g) read it directly. Cases (d)/(f)/(h) need a scenario the
// real seed doesn't naturally contain (a name collision; a subject with >1 claim_type), so those
// hand-insert uniquely-named fixture rows the same way RepositoryQueryTest does.
class ConflictLookupTest : AbstractContainerTest() {

    @Autowired
    lateinit var conflictLookup: ConflictLookup

    @Autowired
    lateinit var entityRecordRepository: EntityRecordRepository

    @Autowired
    lateinit var entityAliasRepository: EntityAliasRepository

    @Autowired
    lateinit var variantClaimRepository: VariantClaimRepository

    // (a) exact-name resolution
    @Test
    fun `find resolves an exact entity name and returns all matching claim rows`() {
        val results = conflictLookup.find("Achilles", "death")

        assertThat(results).isNotEmpty
        assertThat(results.map { it.claimValue }.toSet().size).isGreaterThanOrEqualTo(2)
        assertThat(results.map { it.sourceAuthor }).contains("Homer")
    }

    // (b) alias resolution
    @Test
    fun `find resolves Venus to Aphrodite via entity_aliases`() {
        val viaAlias = conflictLookup.find("Venus", "parentage")
        val viaCanonical = conflictLookup.find("Aphrodite", "parentage")

        assertThat(viaAlias).isNotEmpty
        assertThat(viaAlias.map { it.claimValue }.toSet())
            .isEqualTo(viaCanonical.map { it.claimValue }.toSet())
    }

    // (c) trigram fuzzy resolution
    @Test
    fun `find resolves a near-miss spelling of Aphrodite via trigram similarity`() {
        val viaTypo = conflictLookup.find("Aphrodyte", "parentage")
        val viaCanonical = conflictLookup.find("Aphrodite", "parentage")

        assertThat(viaTypo).isNotEmpty
        assertThat(viaTypo.map { it.claimValue }.toSet())
            .isEqualTo(viaCanonical.map { it.claimValue }.toSet())
    }

    @Test
    fun `find returns empty for a too-far spelling with no real trigram match`() {
        val results = conflictLookup.find("Zzzxxqqyy999NotAName", "parentage")

        assertThat(results).isEmpty()
    }

    // (d) resolution precedence: exact beats alias
    @Test
    fun `find prefers an exact entity name match over a same-named alias to a different entity`() {
        val exactTarget = entityRecordRepository.save(EntityRecord(name = "TestPrecedenceExact", type = "olympian"))
        variantClaimRepository.save(
            VariantClaim(
                subjectEntityId = exactTarget.id,
                claimType = "parentage",
                claimValue = "the exact-match value",
                sourceId = "hesiod-theogony",
            )
        )
        val aliasTarget = entityRecordRepository.save(EntityRecord(name = "TestPrecedenceAliasTarget", type = "olympian"))
        variantClaimRepository.save(
            VariantClaim(
                subjectEntityId = aliasTarget.id,
                claimType = "parentage",
                claimValue = "the alias-target value",
                sourceId = "hesiod-theogony",
            )
        )
        entityAliasRepository.save(EntityAlias(entityId = aliasTarget.id, alias = "TestPrecedenceExact"))

        val results = conflictLookup.find("TestPrecedenceExact", "parentage")

        assertThat(results.map { it.claimValue }).containsExactly("the exact-match value")
    }

    // (e) normalize() via the claim_type_aliases DB table
    @Test
    fun `find normalizes a surface-form claim type via the claim_type_aliases table`() {
        val viaSurfaceForm = conflictLookup.find("Aphrodite", "parents")
        val viaCanonical = conflictLookup.find("Aphrodite", "parentage")

        assertThat(viaSurfaceForm).isNotEmpty
        assertThat(viaSurfaceForm.map { it.claimValue }.toSet())
            .isEqualTo(viaCanonical.map { it.claimValue }.toSet())
    }

    @Test
    fun `find matches a canonical claim type directly even though it has no self-row in claim_type_aliases`() {
        // 'death' is a canonical target, never an alias key, in claim_type_aliases -- normalize()
        // must identity-fallback rather than requiring a self-row.
        val results = conflictLookup.find("Achilles", "death")

        assertThat(results).isNotEmpty
    }

    // (f) claim-type-filtered fetch is precise
    @Test
    fun `find filters strictly to the requested claim type and excludes others for the same subject`() {
        val subject = entityRecordRepository.save(EntityRecord(name = "TestPrecisionSubject", type = "hero"))
        variantClaimRepository.save(
            VariantClaim(subjectEntityId = subject.id, claimType = "death", claimValue = "died in battle", sourceId = "homer-iliad")
        )
        variantClaimRepository.save(
            VariantClaim(subjectEntityId = subject.id, claimType = "death", claimValue = "died of old age", sourceId = "ovid-metamorphoses")
        )
        variantClaimRepository.save(
            VariantClaim(subjectEntityId = subject.id, claimType = "marriage", claimValue = "married a nymph", sourceId = "hesiod-theogony")
        )

        val deathClaims = conflictLookup.find("TestPrecisionSubject", "death")

        assertThat(deathClaims.map { it.claimValue }).containsExactlyInAnyOrder("died in battle", "died of old age")
    }

    @Test
    fun `find returns empty for a claim type the subject has no rows under, protecting grounded refusals`() {
        // Achilles has only 'death' rows in the real seed -- an unrelated claim type must not
        // spuriously surface his death conflict (ADR-007 SS5 grounded-refusal guard).
        val results = conflictLookup.find("Achilles", "appearance")

        assertThat(results).isEmpty()
    }

    // (g) no source-count gate
    @Test
    fun `find surfaces the Io floor case even though both claims cite the same single source`() {
        val results = conflictLookup.find("Io", "parentage")

        val claimValues = results.map { it.claimValue }
        assertThat(claimValues).anyMatch { it.contains("Inachus") }
        assertThat(claimValues).anyMatch { it.contains("Piren") }
    }

    // (h) subject-only fetch
    @Test
    fun `findAllForEntity returns every claim type for the resolved entity`() {
        val subject = entityRecordRepository.save(EntityRecord(name = "TestSubjectOnlyEntity", type = "hero"))
        variantClaimRepository.save(
            VariantClaim(subjectEntityId = subject.id, claimType = "death", claimValue = "died in battle", sourceId = "homer-iliad")
        )
        variantClaimRepository.save(
            VariantClaim(subjectEntityId = subject.id, claimType = "marriage", claimValue = "married a nymph", sourceId = "hesiod-theogony")
        )

        val all = conflictLookup.findAllForEntity("TestSubjectOnlyEntity")

        assertThat(all.map { it.claimValue }).containsExactlyInAnyOrder("died in battle", "married a nymph")
    }

    // (i) unknown entity / empty result handled gracefully
    @Test
    fun `find and findAllForEntity return empty lists for an unknown entity, never throwing`() {
        assertThat(conflictLookup.find("Definitely Not A Real Entity Xyz", "parentage")).isEmpty()
        assertThat(conflictLookup.findAllForEntity("Definitely Not A Real Entity Xyz")).isEmpty()
    }
}
