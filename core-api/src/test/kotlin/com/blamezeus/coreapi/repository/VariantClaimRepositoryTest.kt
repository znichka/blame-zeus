package com.blamezeus.coreapi.repository

import com.blamezeus.coreapi.AbstractContainerTest
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired

// Track G3 (TODO-stage4.md, the stage's "Done when" bar): unblocked once V12 (Track
// C4) and VariantClaim (Track D5) both exist -- V12's reviewed floor-conflict rows
// (DEV-040/041) are already there, no fixture seeding needed.
class VariantClaimRepositoryTest : AbstractContainerTest() {

    @Autowired
    lateinit var variantClaimRepository: VariantClaimRepository

    @Test
    fun `findByEntityNameIgnoreCase finds at least 2 distinct Aphrodite parentage claims`() {
        val claims = variantClaimRepository.findByEntityNameIgnoreCase("Aphrodite")
        val parentage = claims.filter { it.claimType == "parentage" }

        assertThat(parentage.map { it.claimValue }.toSet().size).isGreaterThanOrEqualTo(2)
        val sourceIds = parentage.map { it.sourceId }.toSet()
        assertThat(sourceIds).contains("hesiod-theogony", "homer-iliad")
    }

    @Test
    fun `findByEntityNameIgnoreCase finds at least 2 distinct Io parentage claims`() {
        val claims = variantClaimRepository.findByEntityNameIgnoreCase("Io")
        val parentage = claims.filter { it.claimType == "parentage" }

        assertThat(parentage.map { it.claimValue }.toSet().size).isGreaterThanOrEqualTo(2)
    }

    @Test
    fun `findByEntityNameIgnoreCase finds at least 2 distinct Achilles death claims`() {
        val claims = variantClaimRepository.findByEntityNameIgnoreCase("Achilles")
        val death = claims.filter { it.claimType == "death" }

        assertThat(death.map { it.claimValue }.toSet().size).isGreaterThanOrEqualTo(2)
    }

    @Test
    fun `all seeded rows carry trust_tier 1`() {
        val claims = variantClaimRepository.findByEntityNameIgnoreCase("Aphrodite")
        assertThat(claims).allMatch { it.trustTier == 1.toShort() }
    }
}
